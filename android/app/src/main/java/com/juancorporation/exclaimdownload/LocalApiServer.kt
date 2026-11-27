package com.juancorporation.exclaimdownload

import android.content.Context
import android.os.Build
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.URL
import java.net.URLDecoder
import java.nio.charset.StandardCharsets
import java.util.Locale
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class LocalApiServer(
    private val app: DownloadApp,
    private val engine: DownloadManagerEngine,
) {
    private val prefs = app.getSharedPreferences("exclaim_download_prefs", Context.MODE_PRIVATE)
    private val clientPool = Executors.newCachedThreadPool()
    private val serverSocket = ServerSocket(0, 50, InetAddress.getByName("127.0.0.1"))
    @Volatile private var running = true

    val port: Int = serverSocket.localPort

    fun start() {
        Thread({
            while (running && !serverSocket.isClosed) {
                try {
                    val socket = serverSocket.accept()
                    clientPool.submit { handleClient(socket) }
                } catch (_: Exception) {
                    if (!running) break
                }
            }
        }, "exclaim-http-accept").apply {
            isDaemon = true
            start()
        }
    }

    fun stop() {
        running = false
        runCatching { serverSocket.close() }
        clientPool.shutdownNow()
    }

    private fun handleClient(socket: Socket) {
        socket.use { sock ->
            sock.soTimeout = 30_000
            val input = BufferedInputStream(sock.getInputStream())
            val output = sock.getOutputStream()

            val requestLine = readLineAscii(input) ?: return
            val parts = requestLine.split(" ")
            if (parts.size < 2) return
            val method = parts[0].uppercase(Locale.ROOT)
            val rawTarget = parts[1]

            val headers = mutableMapOf<String, String>()
            while (true) {
                val line = readLineAscii(input) ?: break
                if (line.isEmpty()) break
                val colon = line.indexOf(':')
                if (colon > 0) {
                    headers[line.substring(0, colon).trim().lowercase(Locale.ROOT)] =
                        line.substring(colon + 1).trim()
                }
            }

            val contentLength = headers["content-length"]?.toIntOrNull()?.coerceIn(0, 1_048_576) ?: 0
            val bodyBytes = if (contentLength > 0) readExactBytes(input, contentLength) else ByteArray(0)

            val queryIdx = rawTarget.indexOf('?')
            val path = if (queryIdx >= 0) rawTarget.substring(0, queryIdx) else rawTarget
            val query = if (queryIdx >= 0) rawTarget.substring(queryIdx + 1) else ""

            try {
                route(method, path, query, bodyBytes, sock, output)
            } catch (exc: Exception) {
                sendJson(output, 500, JSONObject().put("detail", exc.message ?: "Error interno del servidor."))
            }
        }
    }

    private fun route(
        method: String,
        path: String,
        query: String,
        bodyBytes: ByteArray,
        socket: Socket,
        output: OutputStream,
    ) {
        if (method == "GET" && path == "/") {
            serveAsset(output, "static/index.html", "text/html; charset=utf-8")
            return
        }
        if (method == "GET" && path.startsWith("/static/")) {
            val rel = path.removePrefix("/static/")
            if (rel.isEmpty() || ".." in rel || rel.contains('\\')) {
                sendJson(output, 404, JSONObject().put("detail", "No encontrado."))
                return
            }
            val mime = when {
                rel.endsWith(".css") -> "text/css; charset=utf-8"
                rel.endsWith(".js") -> "application/javascript; charset=utf-8"
                rel.endsWith(".png") -> "image/png"
                rel.endsWith(".html") -> "text/html; charset=utf-8"
                else -> "application/octet-stream"
            }
            serveAsset(output, "static/$rel", mime)
            return
        }

        if (method == "GET" && path == "/api/health") {
            val status = runBlocking { withTimeoutOrNull(2000L) { app.ensureEngineReady() } }
            val ready = status?.ready == true
            sendJson(output, 200, JSONObject().put("status", "ok").put("tools", buildToolsJson(ready)))
            return
        }

        if (method == "GET" && path == "/api/app-info") {
            val status = runBlocking { withTimeoutOrNull(2500L) { app.ensureEngineReady() } }
            val ready = status?.ready == true
            val theme = prefs.getString("theme", "dark") ?: "dark"
            val payload = JSONObject().apply {
                put("name", "!Download")
                put("developer", "Juan Corporation")
                put("version", BuildConfig.VERSION_NAME)
                put("platform", "android")
                put("desktop_mode", true)
                put("frozen", true)
                put("can_self_update", true)
                put("github_repo", AppUpdater.GITHUB_REPO)
                put("download_dir", "Download/!Download")
                put(
                    "settings",
                    JSONObject()
                        .put("theme", theme)
                        .put("download_dir", "Download/!Download"),
                )
                put("tools", buildToolsJson(ready))
            }
            sendJson(output, 200, payload)
            return
        }

        if (method == "POST" && path == "/api/settings") {
            val req = JSONObject(bodyBytes.toString(StandardCharsets.UTF_8))
            val theme = req.optString("theme", "").trim()
            if (theme in setOf("dark", "light", "system")) {
                prefs.edit().putString("theme", theme).apply()
            }
            val currentTheme = prefs.getString("theme", "dark") ?: "dark"
            val resp = JSONObject()
                .put("settings", JSONObject().put("theme", currentTheme).put("download_dir", "Download/!Download"))
                .put("download_dir", "Download/!Download")
            sendJson(output, 200, resp)
            return
        }

        if (method == "POST" && path == "/api/info") {
            val req = JSONObject(bodyBytes.toString(StandardCharsets.UTF_8))
            val url = try {
                MediaParser.validateUrl(req.optString("url", ""))
            } catch (exc: IllegalArgumentException) {
                sendJson(output, 400, JSONObject().put("detail", exc.message))
                return
            }
            val playlistMode = req.optString("playlist_mode", "auto").ifBlank { "auto" }
            val canToggle = MediaParser.urlHasVideoAndList(url)
            val wantsPlaylist = MediaParser.shouldExtractPlaylist(url, playlistMode)

            val engineStatus = runBlocking { app.ensureEngineReady() }
            if (!engineStatus.ready) {
                sendJson(output, 503, JSONObject().put("detail", engineStatus.error ?: "Inicializando motor multimedia..."))
                return
            }

            try {
                val ydlReq = YoutubeDLRequest(url).apply {
                    addOption("--dump-single-json")
                    if (wantsPlaylist) {
                        addOption("--flat-playlist")
                        addOption("--yes-playlist")
                        addOption("--playlist-end", "200")
                        addOption("--ignore-errors")
                    } else {
                        addOption("--no-playlist")
                        addOption("--playlist-items", "1")
                    }
                    addOption("--skip-download")
                    addOption("--no-warnings")
                    addOption("--socket-timeout", "25")
                }
                val resp = YoutubeDL.getInstance().execute(ydlReq)
                val infoJson = MediaParser.parseMediaInfoJson(url, resp.out, canToggle, playlistMode)
                sendJson(output, 200, infoJson)
            } catch (exc: Exception) {
                sendJson(output, 422, JSONObject().put("detail", MediaParser.translateYtDlpError(exc.message)))
            }
            return
        }

        if (method == "GET" && path == "/api/thumbnail") {
            handleThumbnail(query, output)
            return
        }

        if (method == "POST" && path == "/api/downloads") {
            val req = JSONObject(bodyBytes.toString(StandardCharsets.UTF_8))
            val url = try {
                MediaParser.validateUrl(req.optString("url", ""))
            } catch (exc: IllegalArgumentException) {
                sendJson(output, 400, JSONObject().put("detail", exc.message))
                return
            }

            val height = if (req.has("height") && !req.isNull("height")) req.optInt("height") else null
            val isPlaylist = req.optBoolean("is_playlist", false)
            val playlistItemsJson = req.optJSONArray("playlist_items")
            val playlistItems = if (playlistItemsJson != null) {
                (0 until playlistItemsJson.length())
                    .mapNotNull { idx -> playlistItemsJson.optInt(idx, -1).takeIf { it in 1..1000 } }
                    .distinct()
                    .sorted()
            } else {
                null
            }
            val jobReq = DownloadManagerEngine.JobRequest(
                url = url,
                mode = req.optString("mode", "video"),
                height = height,
                container = req.optString("container", "mp4"),
                audioFormat = req.optString("audio_format", "mp3"),
                audioBitrate = req.optInt("audio_bitrate", 192),
                embedMetadata = req.optBoolean("embed_metadata", true),
                titleHint = req.optString("title_hint", "").ifBlank { null },
                isPlaylist = isPlaylist,
                playlistItems = playlistItems,
            )
            val job = engine.createJob(jobReq)
            sendJson(output, 200, job.toJson())
            return
        }

        if (method == "GET" && path == "/api/downloads") {
            sendBytes(output, 200, "application/json; charset=utf-8", engine.listRecentJobs().toString().toByteArray())
            return
        }

        if (method == "GET" && path.startsWith("/api/downloads/") && path.endsWith("/events")) {
            val jobId = path.removePrefix("/api/downloads/").removeSuffix("/events")
            handleSse(jobId, socket, output)
            return
        }

        if (method == "POST" && path.startsWith("/api/downloads/") && path.endsWith("/cancel")) {
            val jobId = path.removePrefix("/api/downloads/").removeSuffix("/cancel")
            val job = engine.cancelJob(jobId)
            if (job == null) {
                sendJson(output, 404, JSONObject().put("detail", "Descarga no encontrada."))
            } else {
                sendJson(output, 200, job.toJson())
            }
            return
        }

        if (method == "GET" && path.startsWith("/api/downloads/")) {
            val jobId = path.removePrefix("/api/downloads/")
            val job = engine.getJob(jobId)
            if (job == null) {
                sendJson(output, 404, JSONObject().put("detail", "Descarga no encontrada."))
            } else {
                sendJson(output, 200, job.toJson())
            }
            return
        }

        if (method == "GET" && path == "/api/updates/check") {
            sendJson(output, 200, AppUpdater.checkAppUpdate())
            return
        }

        if (method == "POST" && path == "/api/updates/engine") {
            val res = runBlocking { AppUpdater.updateEngine(app) }
            sendJson(output, 200, res)
            return
        }

        if (method == "POST" && path == "/api/updates/app") {
            val req = JSONObject(bodyBytes.toString(StandardCharsets.UTF_8))
            val assetUrl = req.optString("asset_url", "")
            val assetName = req.optString("asset_name", "")
            try {
                val res = AppUpdater.downloadAndInstallApk(app, assetUrl, assetName)
                sendJson(output, 200, res)
            } catch (exc: IllegalArgumentException) {
                sendJson(output, 400, JSONObject().put("detail", exc.message))
            } catch (exc: Exception) {
                sendJson(output, 502, JSONObject().put("detail", "No se pudo descargar la actualización: ${exc.message}"))
            }
            return
        }

        if (method == "POST" && path == "/api/system/open-file") {
            val req = JSONObject(bodyBytes.toString(StandardCharsets.UTF_8))
            val opened = engine.openSavedFile(req.optString("path", ""))
            if (opened) {
                sendJson(output, 200, JSONObject().put("opened", true))
            } else {
                sendJson(output, 404, JSONObject().put("detail", "No se encontró el archivo para abrir."))
            }
            return
        }

        if (method == "POST" && path == "/api/system/open-folder") {
            val opened = engine.openDownloadsFolder()
            sendJson(output, 200, JSONObject().put("opened", opened))
            return
        }

        sendJson(output, 404, JSONObject().put("detail", "Ruta no encontrada."))
    }

    private fun buildToolsJson(ready: Boolean): JSONObject {
        val ytdlpVer = if (ready) runCatching { YoutubeDL.getInstance().version(app) }.getOrNull() else null
        return JSONObject().apply {
            put(
                "yt_dlp",
                JSONObject()
                    .put("available", ready)
                    .put("version", ytdlpVer ?: if (ready) "Listo" else JSONObject.NULL)
                    .put("using_override", false),
            )
            put(
                "ffmpeg",
                JSONObject()
                    .put("available", ready)
                    .put("version", if (ready) "FFmpeg Android (${Build.SUPPORTED_ABIS.firstOrNull() ?: "arm64"})" else JSONObject.NULL),
            )
            put(
                "ffprobe",
                JSONObject()
                    .put("available", ready)
                    .put("version", if (ready) "Integrado" else JSONObject.NULL),
            )
            put(
                "deno",
                JSONObject()
                    .put("available", ready)
                    .put("version", if (ready) "Motor Python nativo" else JSONObject.NULL),
            )
        }
    }

    private fun handleThumbnail(query: String, output: OutputStream) {
        val rawUrl = parseQueryParam(query, "url")
        val cleaned = try {
            MediaParser.validateUrl(rawUrl ?: "")
        } catch (exc: IllegalArgumentException) {
            sendJson(output, 400, JSONObject().put("detail", exc.message))
            return
        }

        val conn = (URL(cleaned).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = true
            connectTimeout = 10_000
            readTimeout = 10_000
            setRequestProperty(
                "User-Agent",
                "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
            )
        }
        if (conn.responseCode !in 200..299) {
            sendJson(output, 502, JSONObject().put("detail", "No se pudo descargar la miniatura."))
            return
        }

        val contentType = conn.contentType?.substringBefore(';')?.trim()?.lowercase(Locale.ROOT).orEmpty()
        if (!contentType.startsWith("image/")) {
            sendJson(output, 415, JSONObject().put("detail", "Imagen no válida."))
            return
        }

        val bytes = conn.inputStream.use { input ->
            val buf = ByteArrayOutputStream()
            val tmp = ByteArray(8192)
            var total = 0
            while (true) {
                val read = input.read(tmp)
                if (read <= 0) break
                total += read
                if (total > 5 * 1024 * 1024) {
                    sendJson(output, 413, JSONObject().put("detail", "Miniatura demasiado grande."))
                    return
                }
                buf.write(tmp, 0, read)
            }
            buf.toByteArray()
        }

        sendBytes(
            output,
            200,
            contentType,
            bytes,
            extraHeaders = mapOf("Cache-Control" to "public, max-age=3600"),
        )
    }

    private fun handleSse(jobId: String, socket: Socket, output: OutputStream) {
        val sub = engine.subscribe(jobId)
        if (sub == null) {
            sendJson(output, 404, JSONObject().put("detail", "Descarga no encontrada."))
            return
        }
        val (queue, initial) = sub
        socket.soTimeout = 0

        val header = buildString {
            append("HTTP/1.1 200 OK\r\n")
            append("Content-Type: text/event-stream; charset=utf-8\r\n")
            append("Cache-Control: no-cache\r\n")
            append("Connection: close\r\n\r\n")
        }
        output.write(header.toByteArray(StandardCharsets.UTF_8))
        output.write("data: ${initial}\n\n".toByteArray(StandardCharsets.UTF_8))
        output.flush()

        if (initial.optString("status") in DownloadManagerEngine.TERMINAL_STATUSES) {
            return
        }

        try {
            while (running) {
                val frame = queue.poll(15, TimeUnit.SECONDS)
                if (frame == null) {
                    output.write(": ping\n\n".toByteArray(StandardCharsets.UTF_8))
                    output.flush()
                    continue
                }
                output.write("data: $frame\n\n".toByteArray(StandardCharsets.UTF_8))
                output.flush()
                val status = runCatching { JSONObject(frame).optString("status") }.getOrDefault("")
                if (status in DownloadManagerEngine.TERMINAL_STATUSES) {
                    break
                }
            }
        } catch (_: IOException) {
            // Client disconnected
        } finally {
            engine.unsubscribe(jobId, queue)
        }
    }

    private fun serveAsset(output: OutputStream, assetPath: String, contentType: String) {
        val bytes = try {
            app.assets.open(assetPath).use { it.readBytes() }
        } catch (_: IOException) {
            sendJson(output, 404, JSONObject().put("detail", "Recurso no encontrado."))
            return
        }
        sendBytes(output, 200, contentType, bytes)
    }

    private fun sendJson(output: OutputStream, status: Int, json: JSONObject) {
        sendBytes(output, status, "application/json; charset=utf-8", json.toString().toByteArray(StandardCharsets.UTF_8))
    }

    private fun sendBytes(
        output: OutputStream,
        status: Int,
        contentType: String,
        body: ByteArray,
        extraHeaders: Map<String, String> = emptyMap(),
    ) {
        val reason = when (status) {
            200 -> "OK"
            400 -> "Bad Request"
            403 -> "Forbidden"
            404 -> "Not Found"
            413 -> "Payload Too Large"
            415 -> "Unsupported Media Type"
            422 -> "Unprocessable Entity"
            502 -> "Bad Gateway"
            503 -> "Service Unavailable"
            else -> "Internal Server Error"
        }
        val headers = buildString {
            append("HTTP/1.1 $status $reason\r\n")
            append("Content-Type: $contentType\r\n")
            append("Content-Length: ${body.size}\r\n")
            append("X-Content-Type-Options: nosniff\r\n")
            extraHeaders.forEach { (k, v) -> append("$k: $v\r\n") }
            append("Connection: close\r\n\r\n")
        }
        output.write(headers.toByteArray(StandardCharsets.UTF_8))
        output.write(body)
        output.flush()
    }

    private fun parseQueryParam(query: String, key: String): String? {
        if (query.isBlank()) return null
        for (pair in query.split("&")) {
            val eq = pair.indexOf('=')
            if (eq <= 0) continue
            val k = URLDecoder.decode(pair.substring(0, eq), "UTF-8")
            if (k == key) {
                return URLDecoder.decode(pair.substring(eq + 1), "UTF-8")
            }
        }
        return null
    }

    private fun readLineAscii(input: InputStream): String? {
        val buf = ByteArrayOutputStream()
        var b = input.read()
        if (b == -1) return null
        while (b != -1 && b != '\n'.code) {
            if (b != '\r'.code) {
                buf.write(b)
            }
            b = input.read()
        }
        return buf.toString(StandardCharsets.US_ASCII.name())
    }

    private fun readExactBytes(input: InputStream, length: Int): ByteArray {
        val out = ByteArray(length)
        var offset = 0
        while (offset < length) {
            val read = input.read(out, offset, length - offset)
            if (read <= 0) break
            offset += read
        }
        return if (offset == length) out else out.copyOf(offset)
    }
}
