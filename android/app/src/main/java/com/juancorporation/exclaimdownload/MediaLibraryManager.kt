package com.juancorporation.exclaimdownload

import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Base64
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
    }

    private data class ResolvedMediaSource(
        val id: String,
        val file: File?,
        val contentUri: Uri?,
        val name: String,
        val ext: String,
        val mime: String,
        val size: Long,
        val mtime: Double,
        val source: String,
        val folderGroup: String?,
    )

    private val playlistLock = Any()
    private val probeCache = ConcurrentHashMap<String, JSONObject>()
    private val playlistsFile = File(app.filesDir, "playlists.json")
    private val importedDir = File(app.filesDir, "imported_media").apply { mkdirs() }

    fun scanLibrary(): JSONArray {
        val sources = collectAllSources()
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
            name = target.name,
            ext = ext,
            mime = MIME_BY_EXT[ext] ?: "application/octet-stream",
            size = target.length(),
            mtime = target.lastModified() / 1000.0,
            source = "imported",
            folderGroup = null,
        )
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
        val mmr = MediaMetadataRetriever()
        return try {
            setDataSource(mmr, src)
            val pic = mmr.embeddedPicture ?: return null
            val mime = if (pic.size > 4 && pic[0] == 0x89.toByte() && pic[1] == 0x50.toByte()) {
                "image/png"
            } else {
                "image/jpeg"
            }
            pic to mime
        } catch (_: Exception) {
            null
        } finally {
            runCatching { mmr.release() }
        }
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
            setRequestProperty("User-Agent", "!Download-Metadata/1.6.0")
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
        val ffmpegCmd = findFfmpegCommand()

        val tempDir = File(app.cacheDir, "tagging_${UUID.randomUUID().toString().take(8)}").apply { mkdirs() }
        val tmpInput = File(tempDir, "in.${src.ext}")
        val tmpOut = File(tempDir, "out.${src.ext}")
        try {
            openInputStream(src)?.use { inp -> tmpInput.outputStream().use { inp.copyTo(it) } }
                ?: throw IOException("No se pudo leer el archivo original.")

            var taggedFile: File? = null
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
                var coverTmp: File? = null
                val supportsCover = src.ext in setOf("mp3", "m4a", "aac", "flac")
                if (supportsCover && coverBytes != null) {
                    coverTmp = File(tempDir, "cover.jpg").apply { writeBytes(coverBytes.first) }
                    cmd.addAll(listOf("-i", coverTmp.absolutePath, "-map", "0:a:0", "-map", "1:v:0", "-c:a", "copy", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic"))
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
                throw IllegalArgumentException("En Android la edición directa sin recodificar está garantizada para MP3.")
            }

            if (src.file != null) {
                taggedFile.copyTo(src.file, overwrite = true)
            } else if (src.contentUri != null) {
                app.contentResolver.openOutputStream(src.contentUri, "wt")?.use { out ->
                    taggedFile.inputStream().use { it.copyTo(out) }
                } ?: throw IOException("No se pudo sobrescribir el archivo en Descargas.")
            }
            probeCache.remove(src.id)
            val refreshed = resolveByPath(src.id) ?: src
            return buildItemJson(refreshed)
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
            File(app.noBackupFilesDir, "youtubedl-android/packages/ffmpeg/usr/bin/ffmpeg"),
            File(app.applicationInfo.nativeLibraryDir, "libffmpeg.so"),
        )
        val bin = candidates.firstOrNull { it.isFile && it.canExecute() } ?: return null
        val libDir = File(app.noBackupFilesDir, "youtubedl-android/packages/ffmpeg/usr/lib")
        val ldPath = listOfNotNull(
            libDir.takeIf { it.isDirectory }?.absolutePath,
            app.applicationInfo.nativeLibraryDir,
        ).joinToString(":")
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
                setRequestProperty("User-Agent", "!Download-Cover/1.6.0")
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
            payload[0] = 0x01 // UTF-16 with BOM
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
                write(0x00) // ISO-8859-1
                write(mimeAscii)
                write(0x00)
                write(0x03) // Cover (front)
                write(0x00) // empty description
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
            out.write(byteArrayOf(3, 0, 0)) // ID3v2.3.0
            out.write(syncSafe)
            out.write(frameData)
            out.write(raw, audioOffset, raw.size - audioOffset)
        }
    }

    private fun collectAllSources(): List<ResolvedMediaSource> {
        val result = mutableListOf<ResolvedMediaSource>()
        val seen = mutableSetOf<String>()

        fun addFile(file: File, source: String, group: String?) {
            if (!file.isFile || file.name.startsWith(".")) return
            val ext = file.extension.lowercase(Locale.ROOT)
            if (ext !in MEDIA_EXTS) return
            if (!seen.add(file.absolutePath)) return
            result.add(
                ResolvedMediaSource(
                    id = file.absolutePath,
                    file = file,
                    contentUri = null,
                    name = file.name,
                    ext = ext,
                    mime = MIME_BY_EXT[ext] ?: "application/octet-stream",
                    size = file.length(),
                    mtime = file.lastModified() / 1000.0,
                    source = source,
                    folderGroup = group,
                )
            )
        }

        fun walkDir(root: File, source: String, maxDepth: Int = 2) {
            if (!root.isDirectory) return
            fun walk(dir: File, depth: Int) {
                dir.listFiles()?.forEach { entry ->
                    if (entry.isDirectory && depth < maxDepth && !entry.name.startsWith(".")) {
                        walk(entry, depth + 1)
                    } else if (entry.isFile) {
                        val group = if (dir != root) dir.name else null
                        addFile(entry, source, group)
                    }
                }
            }
            walk(root, 0)
        }

        walkDir(importedDir, "imported", maxDepth = 1)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val resolver = app.contentResolver
            val projection = arrayOf(
                MediaStore.Downloads._ID,
                MediaStore.Downloads.DISPLAY_NAME,
                MediaStore.Downloads.RELATIVE_PATH,
                MediaStore.Downloads.SIZE,
                MediaStore.Downloads.DATE_MODIFIED,
            )
            val selection = "${MediaStore.Downloads.RELATIVE_PATH} LIKE ?"
            val args = arrayOf("%!Download%")
            runCatching {
                resolver.query(
                    MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                    projection,
                    selection,
                    args,
                    "${MediaStore.Downloads.DATE_MODIFIED} DESC",
                )?.use { cursor ->
                    val idCol = cursor.getColumnIndexOrThrow(MediaStore.Downloads._ID)
                    val nameCol = cursor.getColumnIndexOrThrow(MediaStore.Downloads.DISPLAY_NAME)
                    val relCol = cursor.getColumnIndexOrThrow(MediaStore.Downloads.RELATIVE_PATH)
                    val sizeCol = cursor.getColumnIndexOrThrow(MediaStore.Downloads.SIZE)
                    val modCol = cursor.getColumnIndexOrThrow(MediaStore.Downloads.DATE_MODIFIED)
                    while (cursor.moveToNext()) {
                        val rowId = cursor.getLong(idCol)
                        val name = cursor.getString(nameCol) ?: continue
                        val ext = File(name).extension.lowercase(Locale.ROOT)
                        if (ext !in MEDIA_EXTS) continue
                        val uri = ContentUris.withAppendedId(MediaStore.Downloads.EXTERNAL_CONTENT_URI, rowId)
                        val idStr = uri.toString()
                        if (!seen.add(idStr)) continue
                        val rel = cursor.getString(relCol).orEmpty()
                        val subMatch = Regex("""!Download/([^/]+)/""").find(rel)
                        result.add(
                            ResolvedMediaSource(
                                id = idStr,
                                file = null,
                                contentUri = uri,
                                name = name,
                                ext = ext,
                                mime = MIME_BY_EXT[ext] ?: "application/octet-stream",
                                size = cursor.getLong(sizeCol),
                                mtime = cursor.getLong(modCol).toDouble(),
                                source = "downloaded",
                                folderGroup = subMatch?.groupValues?.getOrNull(1),
                            )
                        )
                    }
                }
            }
        } else {
            @Suppress("DEPRECATION")
            val dlDir = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "!Download")
            walkDir(dlDir, "downloaded", maxDepth = 2)
        }

        return result
    }

    private fun resolveByPath(path: String): ResolvedMediaSource? {
        if (path.isBlank()) return null
        return collectAllSources().firstOrNull { it.id == path }
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

    private fun buildItemJson(src: ResolvedMediaSource): JSONObject {
        val cacheKey = src.id
        val cached = probeCache[cacheKey]
        if (cached != null && cached.optLong("_mtime_key", -1L) == src.mtime.toLong()) {
            return JSONObject(cached.toString())
        }

        val kind = if (src.ext in AUDIO_EXTS) "audio" else "video"
        var title = File(src.name).nameWithoutExtension
        var artist = ""
        var album = ""
        var year = ""
        var genre = ""
        var track = ""
        var duration: Double? = null
        var bitrate: Int? = null
        var hasCover = false

        val mmr = MediaMetadataRetriever()
        runCatching {
            setDataSource(mmr, src)
            mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE)?.trim()?.takeIf { it.isNotEmpty() }?.let { title = it }
            artist = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)?.trim().orEmpty()
            album = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ALBUM)?.trim().orEmpty()
            year = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_YEAR)?.trim().orEmpty()
            genre = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_GENRE)?.trim().orEmpty()
            track = mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_CD_TRACK_NUMBER)?.trim().orEmpty()
            mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()?.let {
                duration = it / 1000.0
            }
            mmr.extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITRATE)?.toLongOrNull()?.let {
                bitrate = (it / 1000L).toInt().coerceAtLeast(1)
            }
            hasCover = mmr.embeddedPicture != null
        }
        runCatching { mmr.release() }

        val json = JSONObject().apply {
            put("path", src.id)
            put("filename", src.name)
            put("title", title)
            put("artist", artist)
            put("album", album)
            put("year", year)
            put("genre", genre)
            put("track", track)
            put("kind", kind)
            put("ext", src.ext.uppercase(Locale.ROOT))
            put("mime", src.mime)
            put("duration", duration ?: JSONObject.NULL)
            put("bitrate", bitrate ?: JSONObject.NULL)
            put("codec", src.ext.uppercase(Locale.ROOT))
            put("size", src.size)
            put("mtime", src.mtime)
            put("has_cover", hasCover)
            put("source", src.source)
            put("folder_group", src.folderGroup ?: JSONObject.NULL)
            put("_mtime_key", src.mtime.toLong())
        }
        if (probeCache.size > 256) probeCache.clear()
        probeCache[cacheKey] = json
        return json
    }
}
