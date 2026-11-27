package com.juancorporation.exclaimdownload

import android.content.ContentUris
import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Base64
import android.util.Size
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileNotFoundException
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.Locale
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

class MediaLibraryManager(private val app: DownloadApp) {

    companion object {
        val AUDIO_EXTS = setOf("mp3", "m4a", "flac", "wav", "opus", "ogg", "aac")
        val VIDEO_EXTS = setOf("mp4", "mkv", "webm", "mov", "m4v")
        val MEDIA_EXTS = AUDIO_EXTS + VIDEO_EXTS

        private val MIME_BY_EXT = mapOf(
            "mp3" to "audio/mpeg",
            "m4a" to "audio/mp4",
            "aac" to "audio/aac",
            "flac" to "audio/flac",
            "wav" to "audio/wav",
            "opus" to "audio/opus",
            "ogg" to "audio/ogg",
            "mp4" to "video/mp4",
            "m4v" to "video/mp4",
            "mkv" to "video/x-matroska",
            "webm" to "video/webm",
            "mov" to "video/quicktime",
        )

        private val NOISE_RE = Regex(
            """(\(|\[)\s*(official\s*(music\s*)?video|official\s*audio|lyric(s)?(\s*video)?|visualizer|audio|video\s*oficial|letra|hd|4k|hq|explicit|remastered(\s*\d{4})?|feat\.?[^\)\]]*)\s*(\)|\])""",
            RegexOption.IGNORE_CASE,
        )
        private val INDEX_RE = Regex("""^\s*\d{1,3}\s*[-._)]\s*""")

        /**
         * Build LD_LIBRARY_PATH containing FFmpeg libs, Python libs (which provide libexpat.so.1
         * required by libfontconfig.so), any sibling package lib dirs, and nativeLibraryDir.
         */
        fun buildFfmpegLdLibraryPath(
            packagesRoot: File,
            nativeLibDir: String?,
            existingLdPath: String? = null,
        ): String {
            val ordered = LinkedHashSet<String>()
            fun addIfDir(dir: File?) {
                if (dir != null && dir.isDirectory) {
                    ordered.add(dir.absolutePath)
                }
            }
            addIfDir(File(packagesRoot, "ffmpeg/usr/lib"))
            addIfDir(File(packagesRoot, "python/usr/lib"))
            if (packagesRoot.isDirectory) {
                packagesRoot.listFiles()?.forEach { pkg ->
                    if (pkg.isDirectory) {
                        addIfDir(File(pkg, "usr/lib"))
                        addIfDir(File(pkg, "lib"))
                    }
                }
            }
            if (!nativeLibDir.isNullOrBlank()) {
                ordered.add(nativeLibDir)
            }
            if (!existingLdPath.isNullOrBlank()) {
                existingLdPath.split(':').forEach { part ->
                    val cleaned = part.trim()
                    if (cleaned.isNotEmpty()) ordered.add(cleaned)
                }
            }
            return ordered.joinToString(":")
        }
    }

    private data class ResolvedMediaSource(
        val id: String,
        val file: File?,
        val contentUri: Uri?,
        val albumArtUri: Uri?,
        val name: String,
        val ext: String,
        val mime: String,
        val size: Long,
        val mtime: Double,
        val source: String,
        val folderPath: String,
        val folderGroup: String?,
        val kind: String,
        val title: String?,
        val artist: String?,
        val album: String?,
        val year: String?,
        val durationSec: Double?,
    )

    private val playlistLock = Any()
    private val sourcesById = ConcurrentHashMap<String, ResolvedMediaSource>()
    private val sidecarTags = ConcurrentHashMap<String, JSONObject>()
    private val playlistsFile = File(app.filesDir, "playlists.json")
    private val importedDir = File(app.filesDir, "imported_media").apply { mkdirs() }
    private val coversDir = File(app.filesDir, "covers").apply { mkdirs() }

    private fun sidecarKey(id: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(id.toByteArray(StandardCharsets.UTF_8))
        return digest.joinToString("") { "%02x".format(it) }.take(24)
    }

    private fun sidecarCoverFile(id: String): File? {
        val key = sidecarKey(id)
        for (ext in arrayOf("jpg", "png")) {
            val f = File(coversDir, "$key.$ext")
            if (f.isFile && f.length() > 32L) return f
        }
        return null
    }

    private fun saveSidecarCover(id: String, bytes: ByteArray, mime: String) {
        val key = sidecarKey(id)
        File(coversDir, "$key.jpg").delete()
        File(coversDir, "$key.png").delete()
        val ext = if ("png" in mime.lowercase(Locale.ROOT)) "png" else "jpg"
        File(coversDir, "$key.$ext").writeBytes(bytes)
    }

    fun scanLibrary(scope: String = "all"): JSONArray {
        val sources = collectAllSources(includeDevice = scope != "app")
        sourcesById.clear()
        for (src in sources) {
            sourcesById[src.id] = src
        }
        val array = JSONArray()
        for (src in sources.sortedByDescending { it.mtime }) {
            array.put(buildItemJson(src))
        }
        return array
    }

    fun saveImportedFile(filename: String, input: InputStream, contentLength: Long): JSONObject {
        val rawName = File(filename.ifBlank { "pista.mp3" }).name
        val cleanName = rawName.replace(Regex("""[<>:"/\\|?*\x00-\x1F]"""), "_").trim().ifBlank { "pista.mp3" }
        val dot = cleanName.lastIndexOf('.')
        val stem = if (dot > 0) cleanName.substring(0, dot) else cleanName
        val ext = if (dot > 0) cleanName.substring(dot + 1).lowercase(Locale.ROOT) else ""
        if (ext !in MEDIA_EXTS) {
            throw IllegalArgumentException("Formato no compatible (.$ext).")
        }

        importedDir.mkdirs()
        var target = File(importedDir, cleanName)
        var counter = 1
        while (target.exists()) {
            target = File(importedDir, "$stem ($counter).$ext")
            counter++
        }

        try {
            target.outputStream().use { out ->
                val buf = ByteArray(32 * 1024)
                var remaining = if (contentLength > 0) contentLength else Long.MAX_VALUE
                while (remaining > 0) {
                    val toRead = minOf(buf.size.toLong(), remaining).toInt()
                    val read = input.read(buf, 0, toRead)
                    if (read <= 0) break
                    out.write(buf, 0, read)
                    if (contentLength > 0) remaining -= read
                }
            }
            if (target.length() <= 0L) {
                target.delete()
                throw IllegalArgumentException("El archivo está vacío.")
            }
        } catch (exc: Exception) {
            target.delete()
            throw exc
        }

        val src = ResolvedMediaSource(
            id = target.absolutePath,
            file = target,
            contentUri = null,
            albumArtUri = null,
            name = target.name,
            ext = ext,
            mime = MIME_BY_EXT[ext] ?: "application/octet-stream",
            size = target.length(),
            mtime = target.lastModified() / 1000.0,
            source = "imported",
            folderPath = "Importados",
            folderGroup = "Importados",
            kind = if (ext in AUDIO_EXTS) "audio" else "video",
            title = null,
            artist = null,
            album = null,
            year = null,
            durationSec = null,
        )
        sourcesById[src.id] = src
        return buildItemJson(src)
    }

    fun streamMedia(path: String, rangeHeader: String?, output: OutputStream) {
        val src = resolveByPath(path) ?: throw FileNotFoundException("Archivo no encontrado.")
        val totalSize = resolveTotalSize(src)
        if (totalSize <= 0L) throw IOException("Archivo vacío.")

        var start = 0L
        var end = totalSize - 1L
        var isPartial = false

        if (!rangeHeader.isNullOrBlank() && rangeHeader.startsWith("bytes=", ignoreCase = true)) {
            val spec = rangeHeader.substring(6).substringBefore(',').trim()
            val dash = spec.indexOf('-')
            if (dash >= 0) {
                val startPart = spec.substring(0, dash).trim()
                val endPart = spec.substring(dash + 1).trim()
                if (startPart.isEmpty() && endPart.isNotEmpty()) {
                    val suffix = endPart.toLongOrNull() ?: 0L
                    start = (totalSize - suffix).coerceAtLeast(0L)
                    end = totalSize - 1L
                } else {
                    start = startPart.toLongOrNull()?.coerceIn(0L, totalSize - 1L) ?: 0L
                    end = endPart.toLongOrNull()?.coerceIn(start, totalSize - 1L) ?: (totalSize - 1L)
                }
                isPartial = true
            }
        }

        val length = (end - start + 1L).coerceAtLeast(0L)
        val header = buildString {
            append(if (isPartial) "HTTP/1.1 206 Partial Content\r\n" else "HTTP/1.1 200 OK\r\n")
            append("Content-Type: ${src.mime}\r\n")
            append("Accept-Ranges: bytes\r\n")
            append("Content-Length: $length\r\n")
            if (isPartial) {
                append("Content-Range: bytes $start-$end/$totalSize\r\n")
            }
            append("X-Content-Type-Options: nosniff\r\n")
            append("Connection: close\r\n\r\n")
        }
        output.write(header.toByteArray(StandardCharsets.UTF_8))

        val input = openInputStream(src) ?: throw IOException("No se pudo abrir el archivo.")
        input.use { stream ->
            var skipped = 0L
            while (skipped < start) {
                val step = stream.skip(start - skipped)
                if (step <= 0L) {
                    if (stream.read() == -1) break
                    skipped += 1L
                } else {
                    skipped += step
                }
            }
            val buf = ByteArray(64 * 1024)
            var left = length
            while (left > 0L) {
                val toRead = minOf(buf.size.toLong(), left).toInt()
                val read = stream.read(buf, 0, toRead)
                if (read <= 0) break
                output.write(buf, 0, read)
                left -= read
            }
        }
        output.flush()
    }

    fun extractCoverBytes(path: String): Pair<ByteArray, String>? {
        val src = resolveByPath(path) ?: return null
        sidecarCoverFile(src.id)?.let { file ->
            val mime = if (file.extension == "png") "image/png" else "image/jpeg"
            return file.readBytes() to mime
        }
        val mmr = MediaMetadataRetriever()
        val embedded = try {
            setDataSource(mmr, src)
            mmr.embeddedPicture?.let { pic ->
                val mime = if (pic.size > 4 && pic[0] == 0x89.toByte() && pic[1] == 0x50.toByte()) {
                    "image/png"
                } else {
                    "image/jpeg"
                }
                pic to mime
            }
        } catch (_: Exception) {
            null
        } finally {
            runCatching { mmr.release() }
        }
        if (embedded != null) return embedded

        if (src.albumArtUri != null) {
            runCatching {
                app.contentResolver.openInputStream(src.albumArtUri)?.use { it.readBytes() }
            }.getOrNull()?.takeIf { it.isNotEmpty() }?.let { return it to "image/jpeg" }
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && src.contentUri != null) {
            val thumbBytes = runCatching {
                val bmp = app.contentResolver.loadThumbnail(src.contentUri, Size(512, 512), null)
                ByteArrayOutputStream().apply {
                    bmp.compress(android.graphics.Bitmap.CompressFormat.JPEG, 88, this)
                }.toByteArray()
            }.getOrNull()
            if (thumbBytes != null && thumbBytes.isNotEmpty()) {
                return thumbBytes to "image/jpeg"
            }
        }

        // Folder artwork fallback for local files
        src.file?.parentFile?.let { parent ->
            for (cand in arrayOf("cover.jpg", "folder.jpg", "front.jpg", "album.jpg", "cover.png", "folder.png")) {
                val f = File(parent, cand)
                if (f.isFile && f.length() in 65L..(5 * 1024 * 1024)) {
                    val mime = if (cand.endsWith(".png")) "image/png" else "image/jpeg"
                    return f.readBytes() to mime
                }
            }
        }
        return null
    }

    fun cleanTrackQuery(raw: String): String {
        var text = raw.trim()
        val dot = text.lastIndexOf('.')
        if (dot > 0) text = text.substring(0, dot)
        text = INDEX_RE.replace(text, "")
        text = NOISE_RE.replace(text, " ")
        text = text.replace('_', ' ').replace(Regex("""\s{2,}"""), " ").trim(' ', '-', '–', '—', '|')
        return text.ifBlank { raw.trim() }
    }

    fun lookupMetadataOnline(query: String, limit: Int = 6): JSONArray {
        val cleaned = cleanTrackQuery(query)
        if (cleaned.isBlank()) return JSONArray()
        val encoded = URLEncoder.encode(cleaned, "UTF-8")
        val url = URL("https://itunes.apple.com/search?term=$encoded&media=music&entity=song&limit=${limit.coerceIn(1, 12)}")
        val conn = (url.openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 10_000
            setRequestProperty("User-Agent", "!Download-Metadata/1.6.1")
        }
        if (conn.responseCode !in 200..299) {
            throw IOException("iTunes API HTTP ${conn.responseCode}")
        }
        val body = conn.inputStream.bufferedReader(StandardCharsets.UTF_8).use { it.readText() }
        val results = JSONObject(body).optJSONArray("results") ?: JSONArray()
        val out = JSONArray()
        for (i in 0 until results.length()) {
            val item = results.optJSONObject(i) ?: continue
            val title = item.optString("trackName", "").trim()
            val artist = item.optString("artistName", "").trim()
            if (title.isBlank() && artist.isBlank()) continue
            var art = item.optString("artworkUrl100", "").ifBlank { item.optString("artworkUrl60", "") }.trim()
            if (art.isNotBlank()) {
                art = art.replace(Regex("""\d+x\d+bb\."""), "600x600bb.")
            }
            val relDate = item.optString("releaseDate", "")
            val year = Regex("""\d{4}""").find(relDate)?.value ?: ""
            val trackNum = item.optInt("trackNumber", 0)
            val trackCount = item.optInt("trackCount", 0)
            val trackStr = when {
                trackNum > 0 && trackCount > 0 -> "$trackNum/$trackCount"
                trackNum > 0 -> "$trackNum"
                else -> ""
            }
            val durMs = item.optDouble("trackTimeMillis", -1.0)
            out.put(
                JSONObject()
                    .put("title", title)
                    .put("artist", artist)
                    .put("album", item.optString("collectionName", "").trim())
                    .put("year", year)
                    .put("genre", item.optString("primaryGenreName", "").trim())
                    .put("track", trackStr)
                    .put("cover_url", art)
                    .put("duration", if (durMs > 0) durMs / 1000.0 else JSONObject.NULL),
            )
        }
        return out
    }

    fun applyMetadata(req: JSONObject): JSONObject {
        val path = req.optString("path", "").trim()
        val src = resolveByPath(path) ?: throw IllegalArgumentException("Archivo no encontrado o fuera de permisos.")
        if (src.ext !in AUDIO_EXTS) {
            throw IllegalArgumentException("Solo se pueden editar metadatos en archivos de audio.")
        }

        val title = if (req.has("title") && !req.isNull("title")) req.optString("title", "") else null
        val artist = if (req.has("artist") && !req.isNull("artist")) req.optString("artist", "") else null
        val album = if (req.has("album") && !req.isNull("album")) req.optString("album", "") else null
        val year = if (req.has("year") && !req.isNull("year")) req.optString("year", "") else null
        val genre = if (req.has("genre") && !req.isNull("genre")) req.optString("genre", "") else null
        val track = if (req.has("track") && !req.isNull("track")) req.optString("track", "") else null
        val coverUrl = if (req.has("cover_url") && !req.isNull("cover_url")) req.optString("cover_url", "") else null
        val coverB64 = if (req.has("cover_base64") && !req.isNull("cover_base64")) req.optString("cover_base64", "") else null

        val coverBytes = fetchCoverBytes(coverUrl, coverB64)
        if (coverBytes != null) {
            saveSidecarCover(src.id, coverBytes.first, coverBytes.second)
        }

        val ffmpegCmd = findFfmpegCommand()
        val tempDir = File(app.cacheDir, "tagging_${UUID.randomUUID().toString().take(8)}").apply { mkdirs() }
        val tmpInput = File(tempDir, "in.${src.ext}")
        val tmpOut = File(tempDir, "out.${src.ext}")
        try {
            openInputStream(src)?.use { inp -> tmpInput.outputStream().use { inp.copyTo(it) } }
                ?: throw IOException("No se pudo leer el archivo original.")

            val taggedFile: File
            if (src.ext == "mp3") {
                writeId3v2Mp3(
                    srcFile = tmpInput,
                    dstFile = tmpOut,
                    title = title,
                    artist = artist,
                    album = album,
                    year = year,
                    genre = genre,
                    track = track,
                    coverBytes = coverBytes,
                )
                taggedFile = tmpOut
            } else if (ffmpegCmd != null) {
                val cmd = mutableListOf(ffmpegCmd.first, "-y", "-v", "error", "-i", tmpInput.absolutePath)
                val supportsCover = src.ext in setOf("mp3", "m4a", "aac", "flac")
                if (supportsCover && coverBytes != null) {
                    val isJpeg = "jpeg" in coverBytes.second || "jpg" in coverBytes.second
                    val coverTmp = File(tempDir, if (isJpeg) "cover.jpg" else "cover.png").apply {
                        writeBytes(coverBytes.first)
                    }
                    cmd.addAll(
                        listOf(
                            "-i", coverTmp.absolutePath,
                            "-map", "0:a:0",
                            "-map", "1:v:0",
                            "-c:a", "copy",
                            "-c:v", if (isJpeg) "copy" else "mjpeg",
                            "-disposition:v:0", "attached_pic",
                        ),
                    )
                } else if (supportsCover) {
                    cmd.addAll(listOf("-map", "0:a:0", "-map", "0:v?", "-c:a", "copy", "-c:v", "copy"))
                } else {
                    cmd.addAll(listOf("-map", "0:a:0", "-c:a", "copy"))
                }
                listOf("title" to title, "artist" to artist, "album" to album, "date" to year, "genre" to genre, "track" to track).forEach { (k, v) ->
                    if (v != null) cmd.addAll(listOf("-metadata", "$k=${v.trim()}"))
                }
                if (src.ext in setOf("m4a", "aac")) {
                    cmd.addAll(listOf("-movflags", "+faststart"))
                }
                cmd.add(tmpOut.absolutePath)

                val pb = ProcessBuilder(cmd).redirectErrorStream(true)
                if (ffmpegCmd.second != null) {
                    pb.environment()["LD_LIBRARY_PATH"] = ffmpegCmd.second!!
                }
                val proc = pb.start()
                val err = proc.inputStream.bufferedReader().use { it.readText() }
                if (proc.waitFor() != 0 || !tmpOut.isFile || tmpOut.length() == 0L) {
                    throw IOException(err.ifBlank { "No se pudieron escribir los metadatos con FFmpeg." })
                }
                taggedFile = tmpOut
            } else {
                throw IllegalArgumentException("El motor FFmpeg aún se está inicializando; inténtalo de nuevo en un momento.")
            }

            var wroteFile = false
            if (src.file != null && src.file.canWrite()) {
                runCatching {
                    taggedFile.copyTo(src.file, overwrite = true)
                    wroteFile = true
                }
            } else if (src.contentUri != null) {
                runCatching {
                    app.contentResolver.openOutputStream(src.contentUri, "wt")?.use { out ->
                        taggedFile.inputStream().use { it.copyTo(out) }
                        wroteFile = true
                    }
                }
            }

            if (!wroteFile) {
                // Save clean tagged copy into !Download/Etiquetados if external file is read-only under Scoped Storage
                val saved = MediaStoreSaver.saveToDownloads(app, taggedFile, subFolder = "Etiquetados")
                val newSrc = ResolvedMediaSource(
                    id = saved.contentUri.toString(),
                    file = null,
                    contentUri = saved.contentUri,
                    albumArtUri = null,
                    name = saved.fileName,
                    ext = src.ext,
                    mime = saved.mimeType,
                    size = saved.sizeBytes,
                    mtime = System.currentTimeMillis() / 1000.0,
                    source = "downloaded",
                    folderPath = "Download/!Download/Etiquetados",
                    folderGroup = "Etiquetados",
                    kind = "audio",
                    title = title,
                    artist = artist,
                    album = album,
                    year = year,
                    durationSec = src.durationSec,
                )
                if (coverBytes != null) saveSidecarCover(newSrc.id, coverBytes.first, coverBytes.second)
                sourcesById[newSrc.id] = newSrc
                return buildItemJson(newSrc, overrideTags = mapOf(
                    "title" to title, "artist" to artist, "album" to album, "year" to year, "genre" to genre, "track" to track,
                ), hasCoverOverride = coverBytes != null || sidecarCoverFile(newSrc.id) != null)
            }

            val overrideMap = mutableMapOf<String, String?>()
            overrideMap["title"] = title
            overrideMap["artist"] = artist
            overrideMap["album"] = album
            overrideMap["year"] = year
            overrideMap["genre"] = genre
            overrideMap["track"] = track
            val built = buildItemJson(src, overrideTags = overrideMap, hasCoverOverride = coverBytes != null || sidecarCoverFile(src.id) != null)
            sidecarTags[src.id] = built
            return built
        } finally {
            tempDir.deleteRecursively()
        }
    }

    fun listPlaylists(): JSONArray = synchronized(playlistLock) {
        if (!playlistsFile.isFile) return@synchronized JSONArray()
        return@synchronized runCatching {
            JSONObject(playlistsFile.readText(StandardCharsets.UTF_8)).optJSONArray("playlists") ?: JSONArray()
        }.getOrDefault(JSONArray())
    }

    fun createPlaylist(req: JSONObject): JSONObject = synchronized(playlistLock) {
        val name = req.optString("name", "").trim()
        if (name.isBlank()) throw IllegalArgumentException("Escribe un nombre para la lista.")
        val rawKind = req.optString("kind", "mixed")
        val kind = if (rawKind in setOf("audio", "video", "mixed")) rawKind else "mixed"
        val items = req.optJSONArray("items") ?: JSONArray()
        val now = System.currentTimeMillis() / 1000.0
        val entry = JSONObject()
            .put("id", UUID.randomUUID().toString().replace("-", "").take(10))
            .put("name", name.take(80))
            .put("kind", kind)
            .put("items", items)
            .put("created_at", now)
            .put("updated_at", now)

        val arr = listPlaylists()
        val next = JSONArray().put(entry)
        for (i in 0 until arr.length()) next.put(arr.get(i))
        savePlaylistsArray(next)
        return@synchronized entry
    }

    fun updatePlaylist(id: String, req: JSONObject): JSONObject? = synchronized(playlistLock) {
        val arr = listPlaylists()
        for (i in 0 until arr.length()) {
            val pl = arr.optJSONObject(i) ?: continue
            if (pl.optString("id") == id) {
                if (req.has("name") && !req.isNull("name")) {
                    val cleaned = req.optString("name", "").trim()
                    if (cleaned.isBlank()) throw IllegalArgumentException("El nombre no puede estar vacío.")
                    pl.put("name", cleaned.take(80))
                }
                if (req.has("kind") && !req.isNull("kind")) {
                    val k = req.optString("kind", "mixed")
                    if (k in setOf("audio", "video", "mixed")) pl.put("kind", k)
                }
                if (req.has("items") && !req.isNull("items")) {
                    pl.put("items", req.optJSONArray("items") ?: JSONArray())
                }
                pl.put("updated_at", System.currentTimeMillis() / 1000.0)
                savePlaylistsArray(arr)
                return@synchronized pl
            }
        }
        return@synchronized null
    }

    fun deletePlaylist(id: String): Boolean = synchronized(playlistLock) {
        val arr = listPlaylists()
        val next = JSONArray()
        var removed = false
        for (i in 0 until arr.length()) {
            val pl = arr.optJSONObject(i) ?: continue
            if (pl.optString("id") == id) removed = true else next.put(pl)
        }
        if (removed) savePlaylistsArray(next)
        return@synchronized removed
    }

    private fun savePlaylistsArray(arr: JSONArray) {
        playlistsFile.writeText(JSONObject().put("playlists", arr).toString(2), StandardCharsets.UTF_8)
    }

    private fun findFfmpegCommand(): Pair<String, String?>? {
        val candidates = listOf(
            File(app.applicationInfo.nativeLibraryDir, "libffmpeg.so"),
            File(app.noBackupFilesDir, "youtubedl-android/packages/ffmpeg/usr/bin/ffmpeg"),
        )
        val bin = candidates.firstOrNull { it.isFile && it.canExecute() } ?: return null
        val packagesRoot = File(app.noBackupFilesDir, "youtubedl-android/packages")
        val ldPath = buildFfmpegLdLibraryPath(
            packagesRoot = packagesRoot,
            nativeLibDir = app.applicationInfo.nativeLibraryDir,
            existingLdPath = System.getenv("LD_LIBRARY_PATH"),
        )
        return bin.absolutePath to ldPath
    }

    private fun fetchCoverBytes(coverUrl: String?, coverBase64: String?): Pair<ByteArray, String>? {
        if (!coverBase64.isNullOrBlank()) {
            var raw = coverBase64.trim()
            var mime = "image/jpeg"
            if (raw.startsWith("data:")) {
                val comma = raw.indexOf(',')
                if (comma > 0) {
                    val header = raw.substring(0, comma).lowercase(Locale.ROOT)
                    if ("png" in header) mime = "image/png"
                    raw = raw.substring(comma + 1)
                }
            }
            val bytes = Base64.decode(raw, Base64.DEFAULT)
            if (bytes.isEmpty() || bytes.size > 5 * 1024 * 1024) {
                throw IllegalArgumentException("La imagen de carátula no es válida o supera los 5 MB.")
            }
            return bytes to mime
        }
        if (!coverUrl.isNullOrBlank()) {
            val valid = MediaParser.validateUrl(coverUrl)
            val conn = (URL(valid).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = true
                connectTimeout = 10_000
                readTimeout = 10_000
                setRequestProperty("User-Agent", "!Download-Cover/1.6.1")
            }
            if (conn.responseCode !in 200..299) {
                throw IOException("No se pudo descargar la imagen de carátula.")
            }
            val ctype = conn.contentType?.substringBefore(';')?.trim()?.lowercase(Locale.ROOT).orEmpty()
            if (!ctype.startsWith("image/")) {
                throw IllegalArgumentException("El enlace de carátula no apunta a una imagen.")
            }
            val bytes = conn.inputStream.use { it.readBytes() }
            if (bytes.size > 5 * 1024 * 1024) {
                throw IllegalArgumentException("La carátula supera 5 MB.")
            }
            return bytes to ctype
        }
        return null
    }

    private fun writeId3v2Mp3(
        srcFile: File,
        dstFile: File,
        title: String?,
        artist: String?,
        album: String?,
        year: String?,
        genre: String?,
        track: String?,
        coverBytes: Pair<ByteArray, String>?,
    ) {
        val raw = srcFile.readBytes()
        var audioOffset = 0
        if (raw.size >= 10 && raw[0] == 'I'.code.toByte() && raw[1] == 'D'.code.toByte() && raw[2] == '3'.code.toByte()) {
            val tagSize = ((raw[6].toInt() and 0x7F) shl 21) or
                ((raw[7].toInt() and 0x7F) shl 14) or
                ((raw[8].toInt() and 0x7F) shl 7) or
                (raw[9].toInt() and 0x7F)
            val hasFooter = (raw[5].toInt() and 0x10) != 0
            audioOffset = (10 + tagSize + if (hasFooter) 10 else 0).coerceAtMost(raw.size)
        }

        val frames = ByteArrayOutputStream()
        fun addTextFrame(frameId: String, value: String?) {
            val cleaned = value?.trim().orEmpty()
            if (cleaned.isEmpty()) return
            val textBytes = cleaned.toByteArray(StandardCharsets.UTF_16)
            val payload = ByteArray(1 + textBytes.size)
            payload[0] = 0x01
            System.arraycopy(textBytes, 0, payload, 1, textBytes.size)
            frames.write(frameId.toByteArray(StandardCharsets.US_ASCII))
            frames.write(ByteBuffer.allocate(4).putInt(payload.size).array())
            frames.write(byteArrayOf(0, 0))
            frames.write(payload)
        }

        addTextFrame("TIT2", title)
        addTextFrame("TPE1", artist)
        addTextFrame("TALB", album)
        addTextFrame("TYER", year)
        addTextFrame("TCON", genre)
        addTextFrame("TRCK", track)

        if (coverBytes != null) {
            val (img, mime) = coverBytes
            val mimeAscii = mime.toByteArray(StandardCharsets.US_ASCII)
            val apicPayload = ByteArrayOutputStream().apply {
                write(0x00)
                write(mimeAscii)
                write(0x00)
                write(0x03)
                write(0x00)
                write(img)
            }.toByteArray()
            frames.write("APIC".toByteArray(StandardCharsets.US_ASCII))
            frames.write(ByteBuffer.allocate(4).putInt(apicPayload.size).array())
            frames.write(byteArrayOf(0, 0))
            frames.write(apicPayload)
        }

        val frameData = frames.toByteArray()
        val sz = frameData.size
        val syncSafe = byteArrayOf(
            ((sz shr 21) and 0x7F).toByte(),
            ((sz shr 14) and 0x7F).toByte(),
            ((sz shr 7) and 0x7F).toByte(),
            (sz and 0x7F).toByte(),
        )
        dstFile.outputStream().use { out ->
            out.write("ID3".toByteArray(StandardCharsets.US_ASCII))
            out.write(byteArrayOf(3, 0, 0))
            out.write(syncSafe)
            out.write(frameData)
            out.write(raw, audioOffset, raw.size - audioOffset)
        }
    }

    private fun normalizeFolderPath(rawRel: String?, fallback: String): Pair<String, String> {
        val cleaned = (rawRel ?: "")
            .replace('\\', '/')
            .trim('/')
        if (cleaned.isBlank()) return fallback to fallback
        val leaf = cleaned.substringAfterLast('/')
        return cleaned to leaf
    }

    private fun collectAllSources(includeDevice: Boolean): List<ResolvedMediaSource> {
        val result = mutableListOf<ResolvedMediaSource>()
        val seenIds = mutableSetOf<String>()
        val seenNamesSizes = mutableSetOf<String>()

        fun addFile(file: File, source: String, folderPath: String, group: String?) {
            if (!file.isFile || file.name.startsWith(".")) return
            val ext = file.extension.lowercase(Locale.ROOT)
            if (ext !in MEDIA_EXTS) return
            if (!seenIds.add(file.absolutePath)) return
            seenNamesSizes.add("${file.name.lowercase(Locale.ROOT)}:${file.length()}")
            result.add(
                ResolvedMediaSource(
                    id = file.absolutePath,
                    file = file,
                    contentUri = null,
                    albumArtUri = null,
                    name = file.name,
                    ext = ext,
                    mime = MIME_BY_EXT[ext] ?: "application/octet-stream",
                    size = file.length(),
                    mtime = file.lastModified() / 1000.0,
                    source = source,
                    folderPath = folderPath,
                    folderGroup = group,
                    kind = if (ext in AUDIO_EXTS) "audio" else "video",
                    title = null,
                    artist = null,
                    album = null,
                    year = null,
                    durationSec = null,
                ),
            )
        }

        fun walkDir(root: File, source: String, baseLabel: String, maxDepth: Int = 3) {
            if (!root.isDirectory) return
            fun walk(dir: File, depth: Int) {
                dir.listFiles()?.forEach { entry ->
                    if (entry.isDirectory && depth < maxDepth && !entry.name.startsWith(".")) {
                        walk(entry, depth + 1)
                    } else if (entry.isFile) {
                        val relDir = if (dir == root) baseLabel else "$baseLabel/${dir.relativeTo(root).path.replace('\\', '/')}"
                        val group = if (dir == root) baseLabel else dir.name
                        addFile(entry, source, relDir, group)
                    }
                }
            }
            walk(root, 0)
        }

        walkDir(importedDir, "imported", "Importados", maxDepth = 1)

        val resolver = app.contentResolver

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val dlProjection = arrayOf(
                MediaStore.Downloads._ID,
                MediaStore.Downloads.DISPLAY_NAME,
                MediaStore.Downloads.RELATIVE_PATH,
                MediaStore.Downloads.SIZE,
                MediaStore.Downloads.DATE_MODIFIED,
            )
            runCatching {
                resolver.query(
                    MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                    dlProjection,
                    "${MediaStore.Downloads.RELATIVE_PATH} LIKE ?",
                    arrayOf("%!Download%"),
                    "${MediaStore.Downloads.DATE_MODIFIED} DESC",
                )?.use { cursor ->
                    val idCol = cursor.getColumnIndexOrThrow(MediaStore.Downloads._ID)
                    val nameCol = cursor.getColumnIndexOrThrow(MediaStore.Downloads.DISPLAY_NAME)
                    val relCol = cursor.getColumnIndexOrThrow(MediaStore.Downloads.RELATIVE_PATH)
                    val sizeCol = cursor.getColumnIndexOrThrow(MediaStore.Downloads.SIZE)
                    val modCol = cursor.getColumnIndexOrThrow(MediaStore.Downloads.DATE_MODIFIED)
                    while (cursor.moveToNext()) {
                        val name = cursor.getString(nameCol) ?: continue
                        val ext = File(name).extension.lowercase(Locale.ROOT)
                        if (ext !in MEDIA_EXTS) continue
                        val uri = ContentUris.withAppendedId(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cursor.getLong(idCol))
                        val idStr = uri.toString()
                        if (!seenIds.add(idStr)) continue
                        val sizeVal = cursor.getLong(sizeCol)
                        seenNamesSizes.add("${name.lowercase(Locale.ROOT)}:$sizeVal")
                        val (folderPath, group) = normalizeFolderPath(cursor.getString(relCol), "Download/!Download")
                        result.add(
                            ResolvedMediaSource(
                                id = idStr,
                                file = null,
                                contentUri = uri,
                                albumArtUri = null,
                                name = name,
                                ext = ext,
                                mime = MIME_BY_EXT[ext] ?: "application/octet-stream",
                                size = sizeVal,
                                mtime = cursor.getLong(modCol).toDouble(),
                                source = "downloaded",
                                folderPath = folderPath,
                                folderGroup = group,
                                kind = if (ext in AUDIO_EXTS) "audio" else "video",
                                title = null,
                                artist = null,
                                album = null,
                                year = null,
                                durationSec = null,
                            ),
                        )
                    }
                }
            }
        } else {
            @Suppress("DEPRECATION")
            val dlDir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "!Download")
            walkDir(dlDir, "downloaded", "Download/!Download", maxDepth = 3)
        }

        if (includeDevice) {
            queryDeviceAudio(resolver, seenIds, seenNamesSizes, result)
            queryDeviceVideo(resolver, seenIds, seenNamesSizes, result)
        }

        return result
    }

    private fun queryDeviceAudio(
        resolver: android.content.ContentResolver,
        seenIds: MutableSet<String>,
        seenNamesSizes: MutableSet<String>,
        out: MutableList<ResolvedMediaSource>,
    ) {
        val relColName = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            MediaStore.Audio.Media.RELATIVE_PATH
        } else {
            MediaStore.Audio.Media.BUCKET_DISPLAY_NAME
        }
        val projection = arrayOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.DISPLAY_NAME,
            MediaStore.Audio.Media.TITLE,
            MediaStore.Audio.Media.ARTIST,
            MediaStore.Audio.Media.ALBUM,
            MediaStore.Audio.Media.ALBUM_ID,
            MediaStore.Audio.Media.YEAR,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.SIZE,
            MediaStore.Audio.Media.DATE_MODIFIED,
            relColName,
        )
        runCatching {
            resolver.query(
                MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,
                projection,
                "${MediaStore.Audio.Media.SIZE} > 8192",
                null,
                "${MediaStore.Audio.Media.DATE_MODIFIED} DESC",
            )?.use { c ->
                val idCol = c.getColumnIndex(MediaStore.Audio.Media._ID)
                val nameCol = c.getColumnIndex(MediaStore.Audio.Media.DISPLAY_NAME)
                val titleCol = c.getColumnIndex(MediaStore.Audio.Media.TITLE)
                val artistCol = c.getColumnIndex(MediaStore.Audio.Media.ARTIST)
                val albumCol = c.getColumnIndex(MediaStore.Audio.Media.ALBUM)
                val albumIdCol = c.getColumnIndex(MediaStore.Audio.Media.ALBUM_ID)
                val yearCol = c.getColumnIndex(MediaStore.Audio.Media.YEAR)
                val durCol = c.getColumnIndex(MediaStore.Audio.Media.DURATION)
                val sizeCol = c.getColumnIndex(MediaStore.Audio.Media.SIZE)
                val modCol = c.getColumnIndex(MediaStore.Audio.Media.DATE_MODIFIED)
                val relCol = c.getColumnIndex(relColName)
                var count = 0
                while (c.moveToNext() && count < 800) {
                    val name = if (nameCol >= 0) c.getString(nameCol) else null
                    if (name.isNullOrBlank()) continue
                    val ext = File(name).extension.lowercase(Locale.ROOT)
                    if (ext !in AUDIO_EXTS) continue
                    val sizeVal = if (sizeCol >= 0) c.getLong(sizeCol) else 0L
                    val dedupKey = "${name.lowercase(Locale.ROOT)}:$sizeVal"
                    if (!seenNamesSizes.add(dedupKey)) continue
                    val uri = ContentUris.withAppendedId(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, c.getLong(idCol))
                    if (!seenIds.add(uri.toString())) continue
                    val relRaw = if (relCol >= 0) c.getString(relCol) else null
                    val isAppDl = relRaw?.contains("!Download", ignoreCase = true) == true
                    val (folderPath, group) = normalizeFolderPath(relRaw, "Música")
                    val albumId = if (albumIdCol >= 0) c.getLong(albumIdCol) else -1L
                    @Suppress("DEPRECATION")
                    val artUri = if (albumId > 0L) ContentUris.withAppendedId(Uri.parse("content://media/external/audio/albumart"), albumId) else null
                    val rawArtist = if (artistCol >= 0) c.getString(artistCol)?.trim() else null
                    val cleanArtist = if (rawArtist == "<unknown>") "" else rawArtist.orEmpty()
                    val yr = if (yearCol >= 0) c.getInt(yearCol).let { if (it > 0) it.toString() else "" } else ""
                    val durMs = if (durCol >= 0) c.getLong(durCol) else 0L

                    out.add(
                        ResolvedMediaSource(
                            id = uri.toString(),
                            file = null,
                            contentUri = uri,
                            albumArtUri = artUri,
                            name = name,
                            ext = ext,
                            mime = MIME_BY_EXT[ext] ?: "audio/mpeg",
                            size = sizeVal,
                            mtime = if (modCol >= 0) c.getLong(modCol).toDouble() else 0.0,
                            source = if (isAppDl) "downloaded" else "device",
                            folderPath = folderPath,
                            folderGroup = group,
                            kind = "audio",
                            title = if (titleCol >= 0) c.getString(titleCol)?.trim() else null,
                            artist = cleanArtist,
                            album = if (albumCol >= 0) c.getString(albumCol)?.trim() else null,
                            year = yr,
                            durationSec = if (durMs > 0) durMs / 1000.0 else null,
                        ),
                    )
                    count++
                }
            }
        }
    }

    private fun queryDeviceVideo(
        resolver: android.content.ContentResolver,
        seenIds: MutableSet<String>,
        seenNamesSizes: MutableSet<String>,
        out: MutableList<ResolvedMediaSource>,
    ) {
        val relColName = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            MediaStore.Video.Media.RELATIVE_PATH
        } else {
            MediaStore.Video.Media.BUCKET_DISPLAY_NAME
        }
        val projection = arrayOf(
            MediaStore.Video.Media._ID,
            MediaStore.Video.Media.DISPLAY_NAME,
            MediaStore.Video.Media.TITLE,
            MediaStore.Video.Media.DURATION,
            MediaStore.Video.Media.SIZE,
            MediaStore.Video.Media.DATE_MODIFIED,
            relColName,
        )
        runCatching {
            resolver.query(
                MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
                projection,
                "${MediaStore.Video.Media.SIZE} > 8192",
                null,
                "${MediaStore.Video.Media.DATE_MODIFIED} DESC",
            )?.use { c ->
                val idCol = c.getColumnIndex(MediaStore.Video.Media._ID)
                val nameCol = c.getColumnIndex(MediaStore.Video.Media.DISPLAY_NAME)
                val titleCol = c.getColumnIndex(MediaStore.Video.Media.TITLE)
                val durCol = c.getColumnIndex(MediaStore.Video.Media.DURATION)
                val sizeCol = c.getColumnIndex(MediaStore.Video.Media.SIZE)
                val modCol = c.getColumnIndex(MediaStore.Video.Media.DATE_MODIFIED)
                val relCol = c.getColumnIndex(relColName)
                var count = 0
                while (c.moveToNext() && count < 400) {
                    val name = if (nameCol >= 0) c.getString(nameCol) else null
                    if (name.isNullOrBlank()) continue
                    val ext = File(name).extension.lowercase(Locale.ROOT)
                    if (ext !in VIDEO_EXTS) continue
                    val sizeVal = if (sizeCol >= 0) c.getLong(sizeCol) else 0L
                    val dedupKey = "${name.lowercase(Locale.ROOT)}:$sizeVal"
                    if (!seenNamesSizes.add(dedupKey)) continue
                    val uri = ContentUris.withAppendedId(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, c.getLong(idCol))
                    if (!seenIds.add(uri.toString())) continue
                    val relRaw = if (relCol >= 0) c.getString(relCol) else null
                    val isAppDl = relRaw?.contains("!Download", ignoreCase = true) == true
                    val (folderPath, group) = normalizeFolderPath(relRaw, "Videos")
                    val durMs = if (durCol >= 0) c.getLong(durCol) else 0L

                    out.add(
                        ResolvedMediaSource(
                            id = uri.toString(),
                            file = null,
                            contentUri = uri,
                            albumArtUri = null,
                            name = name,
                            ext = ext,
                            mime = MIME_BY_EXT[ext] ?: "video/mp4",
                            size = sizeVal,
                            mtime = if (modCol >= 0) c.getLong(modCol).toDouble() else 0.0,
                            source = if (isAppDl) "downloaded" else "device",
                            folderPath = folderPath,
                            folderGroup = group,
                            kind = "video",
                            title = if (titleCol >= 0) c.getString(titleCol)?.trim() else null,
                            artist = "",
                            album = "",
                            year = "",
                            durationSec = if (durMs > 0) durMs / 1000.0 else null,
                        ),
                    )
                    count++
                }
            }
        }
    }

    private fun resolveByPath(path: String): ResolvedMediaSource? {
        if (path.isBlank()) return null
        sourcesById[path]?.let { return it }
        return collectAllSources(includeDevice = true).firstOrNull { it.id == path }
    }

    private fun resolveTotalSize(src: ResolvedMediaSource): Long {
        if (src.file != null) return src.file.length()
        if (src.contentUri != null) {
            app.contentResolver.openAssetFileDescriptor(src.contentUri, "r")?.use { afd ->
                if (afd.length >= 0L) return afd.length
            }
        }
        return src.size
    }

    private fun openInputStream(src: ResolvedMediaSource): InputStream? {
        return if (src.file != null) {
            FileInputStream(src.file)
        } else if (src.contentUri != null) {
            app.contentResolver.openInputStream(src.contentUri)
        } else {
            null
        }
    }

    private fun setDataSource(mmr: MediaMetadataRetriever, src: ResolvedMediaSource) {
        if (src.file != null) {
            mmr.setDataSource(src.file.absolutePath)
        } else if (src.contentUri != null) {
            mmr.setDataSource(app, src.contentUri)
        }
    }

    private fun buildItemJson(
        src: ResolvedMediaSource,
        overrideTags: Map<String, String?>? = null,
        hasCoverOverride: Boolean? = null,
    ): JSONObject {
        val patched = sidecarTags[src.id]
        val hasSidecarCover = sidecarCoverFile(src.id) != null
        val defaultTitle = File(src.name).nameWithoutExtension
        var title = overrideTags?.get("title")?.takeIf { !it.isNullOrBlank() }
            ?: patched?.optString("title")?.takeIf { !it.isNullOrBlank() }
            ?: src.title?.takeIf { it.isNotBlank() }
            ?: defaultTitle
        var artist = overrideTags?.get("artist")
            ?: patched?.optString("artist")
            ?: src.artist.orEmpty()
        var album = overrideTags?.get("album")
            ?: patched?.optString("album")
            ?: src.album.orEmpty()
        var year = overrideTags?.get("year")
            ?: patched?.optString("year")
            ?: src.year.orEmpty()
        var genre = overrideTags?.get("genre")
            ?: patched?.optString("genre")
            ?: ""
        var track = overrideTags?.get("track")
            ?: patched?.optString("track")
            ?: ""
        var duration = src.durationSec
        var bitrate: Int? = null
        var hasCover = hasCoverOverride
            ?: (hasSidecarCover || src.albumArtUri != null || src.kind == "video")

        // Only open MediaMetadataRetriever for app/imported files without pre-queried MediaStore tags
        if (src.source != "device" && overrideTags == null && patched == null) {
            val mmr = MediaMetadataRetriever()
            runCatching {
                setDataSource(mmr, src)
                mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE)?.trim()?.takeIf { it.isNotEmpty() }?.let { title = it }
                mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)?.trim()?.takeIf { it.isNotEmpty() }?.let { artist = it }
                mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ALBUM)?.trim()?.takeIf { it.isNotEmpty() }?.let { album = it }
                mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_YEAR)?.trim()?.takeIf { it.isNotEmpty() }?.let { year = it }
                mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_GENRE)?.trim()?.takeIf { it.isNotEmpty() }?.let { genre = it }
                mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_CD_TRACK_NUMBER)?.trim()?.takeIf { it.isNotEmpty() }?.let { track = it }
                mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()?.let { duration = it / 1000.0 }
                mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITRATE)?.toLongOrNull()?.let { bitrate = (it / 1000L).toInt().coerceAtLeast(1) }
                if (!hasCover && mmr.embeddedPicture != null) hasCover = true
            }
            runCatching { mmr.release() }
        } else if (src.source == "device" && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            hasCover = hasCover || hasSidecarCover || src.albumArtUri != null || src.kind == "video"
        }

        return JSONObject().apply {
            put("path", src.id)
            put("filename", src.name)
            put("title", title)
            put("artist", artist)
            put("album", album)
            put("year", year)
            put("genre", genre)
            put("track", track)
            put("kind", src.kind)
            put("ext", src.ext.uppercase(Locale.ROOT))
            put("mime", src.mime)
            put("duration", duration ?: JSONObject.NULL)
            put("bitrate", bitrate ?: JSONObject.NULL)
            put("codec", src.ext.uppercase(Locale.ROOT))
            put("size", src.size)
            put("mtime", src.mtime)
            put("has_cover", hasCover)
            put("source", src.source)
            put("folder_path", src.folderPath)
            put("folder_group", src.folderGroup ?: JSONObject.NULL)
        }
    }
}
