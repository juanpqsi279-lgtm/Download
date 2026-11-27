package com.juancorporation.exclaimdownload

import org.json.JSONArray
import org.json.JSONObject
import java.net.InetAddress
import java.net.URI
import java.util.Locale
import kotlin.math.max
import kotlin.math.roundToInt

object MediaParser {
    private val BLOCKED_HOSTS = setOf("localhost", "localhost.localdomain")
    private val URL_REGEX = Regex("""https?://[^\s<>"']+""", RegexOption.IGNORE_CASE)
    private val IPV4_REGEX = Regex("""^\d{1,3}(\.\d{1,3}){3}$""")
    private val SEMVER_DIGITS = Regex("""\d+""")

    private val MONTHS_ES = mapOf(
        1 to "ene",
        2 to "feb",
        3 to "mar",
        4 to "abr",
        5 to "may",
        6 to "jun",
        7 to "jul",
        8 to "ago",
        9 to "sep",
        10 to "oct",
        11 to "nov",
        12 to "dic",
    )

    private val PLATFORM_LABELS = mapOf(
        "youtube" to "YouTube",
        "youtubetab" to "YouTube",
        "tiktok" to "TikTok",
        "instagram" to "Instagram",
        "twitter" to "X / Twitter",
        "x" to "X / Twitter",
        "reddit" to "Reddit",
        "twitch" to "Twitch",
        "vimeo" to "Vimeo",
        "soundcloud" to "SoundCloud",
        "facebook" to "Facebook",
        "dailymotion" to "Dailymotion",
        "bilibili" to "Bilibili",
        "bandcamp" to "Bandcamp",
        "generic" to "Enlace directo",
    )

    private val AUDIO_BITRATES = listOf(320, 256, 192, 128, 96)
    private val PLAYLIST_TARGET_HEIGHTS = listOf(2160, 1440, 1080, 720, 480, 360)
    private val YOUTUBE_ID_REGEX = Regex("""^[A-Za-z0-9_-]{11}$""")

    fun urlHasVideoAndList(rawUrl: String): Boolean {
        val uri = runCatching { URI(rawUrl.trim()) }.getOrNull() ?: return false
        val query = uri.rawQuery.orEmpty()
        if (query.isBlank()) return false
        val params = query.split("&").mapNotNull { pair ->
            val eq = pair.indexOf('=')
            if (eq > 0) pair.substring(0, eq) to pair.substring(eq + 1) else null
        }.toMap()
        val hasList = !params["list"].isNullOrBlank()
        if (!hasList) return false
        val path = uri.path.orEmpty().lowercase(Locale.ROOT)
        return !params["v"].isNullOrBlank() || "/watch" in path
    }

    fun shouldExtractPlaylist(rawUrl: String, playlistMode: String = "auto"): Boolean {
        val mode = playlistMode.lowercase(Locale.ROOT)
        if (mode == "single") return false
        if (mode == "playlist") return true
        val uri = runCatching { URI(rawUrl.trim()) }.getOrNull() ?: return true
        val query = uri.rawQuery.orEmpty()
        val listVal = query.split("&").firstNotNullOfOrNull { pair ->
            val eq = pair.indexOf('=')
            if (eq > 0 && pair.substring(0, eq) == "list") pair.substring(eq + 1) else null
        }.orEmpty()
        if (urlHasVideoAndList(rawUrl) && listVal.uppercase(Locale.ROOT).startsWith("RD")) {
            return false
        }
        return true
    }

    fun sanitizeFolderName(name: String?, fallback: String = "Playlist"): String {
        val cleaned = (name ?: "").trim()
            .replace(Regex("""[<>:"/\\|?*\u0000-\u001F]+"""), "_")
            .replace(Regex("""\s+"""), " ")
            .trim(' ', '.')
        if (cleaned.isEmpty()) return fallback
        return cleaned.take(90).trimEnd(' ', '.').ifEmpty { fallback }
    }

    fun extractFirstUrl(sharedText: String?): String? {
        if (sharedText.isNullOrBlank()) return null
        val match = URL_REGEX.find(sharedText) ?: return null
        return match.value.trimEnd('.', ',', ';', ')', ']', '>', '"', '\'', '!')
    }

    fun validateUrl(rawUrl: String): String {
        val cleaned = rawUrl.trim()
        if (cleaned.isEmpty()) {
            throw IllegalArgumentException("Por favor, introduce una URL.")
        }
        if (cleaned.any { it == '\r' || it == '\n' || it == '\u0000' }) {
            throw IllegalArgumentException("La URL contiene caracteres no válidos.")
        }

        val uri = try {
            URI(cleaned)
        } catch (_: Exception) {
            throw IllegalArgumentException("La URL no tiene un formato válido.")
        }

        val scheme = uri.scheme?.lowercase(Locale.ROOT)
        if (scheme != "http" && scheme != "https") {
            throw IllegalArgumentException("La URL debe comenzar por http:// o https://.")
        }

        val host = uri.host?.lowercase(Locale.ROOT)?.trimEnd('.')
        if (host.isNullOrEmpty()) {
            throw IllegalArgumentException("La URL no tiene un dominio válido.")
        }

        if (host in BLOCKED_HOSTS || host.endsWith(".local") || host.endsWith(".internal")) {
            throw IllegalArgumentException("No se permiten direcciones locales o internas.")
        }

        val literal = host.trim('[', ']')
        if (IPV4_REGEX.matches(literal) || literal.contains(':')) {
            val addr = try {
                InetAddress.getByName(literal)
            } catch (_: Exception) {
                throw IllegalArgumentException("Dirección IP no válida.")
            }
            if (
                addr.isAnyLocalAddress ||
                addr.isLoopbackAddress ||
                addr.isLinkLocalAddress ||
                addr.isSiteLocalAddress ||
                addr.isMulticastAddress
            ) {
                throw IllegalArgumentException("No se permiten direcciones IP privadas o locales.")
            }
        }

        return cleaned
    }

    fun formatDuration(seconds: Double?): String? {
        if (seconds == null || seconds < 0) return null
        val total = max(0, seconds.roundToInt())
        val hours = total / 3600
        val minutes = (total % 3600) / 60
        val secs = total % 60
        return if (hours > 0) {
            String.format(Locale.US, "%d:%02d:%02d", hours, minutes, secs)
        } else {
            String.format(Locale.US, "%d:%02d", minutes, secs)
        }
    }

    fun formatUploadDate(raw: String?): String? {
        if (raw == null || raw.length != 8 || !raw.all { it.isDigit() }) return null
        val year = raw.substring(0, 4).toIntOrNull() ?: return null
        val month = raw.substring(4, 6).toIntOrNull() ?: return null
        val day = raw.substring(6, 8).toIntOrNull() ?: return null
        val monthLabel = MONTHS_ES[month] ?: return null
        return "$day $monthLabel $year"
    }

    private fun estimateStreamBytes(fmt: JSONObject, duration: Double?): Long? {
        val size = optPositiveDouble(fmt, "filesize") ?: optPositiveDouble(fmt, "filesize_approx")
        if (size != null && size > 0) return size.toLong()
        val tbr = optPositiveDouble(fmt, "tbr")
            ?: optPositiveDouble(fmt, "vbr")
            ?: optPositiveDouble(fmt, "abr")
        if (tbr != null && tbr > 0 && duration != null && duration > 0) {
            return (tbr * duration * 1000.0 / 8.0).toLong()
        }
        return null
    }

    private fun optPositiveDouble(obj: JSONObject, key: String): Double? {
        if (!obj.has(key) || obj.isNull(key)) return null
        val value = obj.optDouble(key, Double.NaN)
        return if (!value.isNaN() && value > 0.0) value else null
    }

    private fun optNonEmptyString(obj: JSONObject, key: String): String? {
        if (!obj.has(key) || obj.isNull(key)) return null
        val v = obj.optString(key, "").trim()
        return if (v.isEmpty() || v == "null") null else v
    }

    private fun cleanVcodec(vcodec: String?): String? {
        if (vcodec.isNullOrBlank() || vcodec == "none") return null
        val lower = vcodec.lowercase(Locale.ROOT)
        return when {
            lower.startsWith("avc") || "h264" in lower -> "H.264"
            lower.startsWith("vp09") || lower.startsWith("vp9") -> "VP9"
            lower.startsWith("av01") || lower.startsWith("av1") -> "AV1"
            lower.startsWith("hev") || lower.startsWith("hvc") || "h265" in lower -> "HEVC"
            else -> vcodec.substringBefore('.').uppercase(Locale.ROOT)
        }
    }

    private fun cleanAcodec(acodec: String?): String? {
        if (acodec.isNullOrBlank() || acodec == "none") return null
        val lower = acodec.lowercase(Locale.ROOT)
        return when {
            lower.startsWith("mp4a") || "aac" in lower -> "AAC"
            "opus" in lower -> "Opus"
            "vorbis" in lower -> "Vorbis"
            "mp3" in lower -> "MP3"
            "flac" in lower -> "FLAC"
            else -> acodec.substringBefore('.').uppercase(Locale.ROOT)
        }
    }

    private fun cleanDynamicRange(dr: String?): String? {
        if (dr.isNullOrBlank()) return null
        val cleaned = dr.trim().uppercase(Locale.ROOT)
        if (cleaned == "SDR" || cleaned == "NONE") return null
        return if ("HDR" in cleaned || "HLG" in cleaned || "DV" in cleaned || "PQ" in cleaned) {
            "HDR"
        } else {
            cleaned
        }
    }

    private fun codecPreference(vcodec: String?): Int {
        if (vcodec.isNullOrBlank() || vcodec == "none") return 0
        val lower = vcodec.lowercase(Locale.ROOT)
        return when {
            lower.startsWith("avc") || "h264" in lower -> 3
            lower.startsWith("vp09") || lower.startsWith("vp9") -> 2
            lower.startsWith("av01") || lower.startsWith("av1") -> 1
            else -> 0
        }
    }

    private fun resolutionLabels(height: Int): Pair<String, String> = when {
        height >= 4320 -> "8K (${height}p)" to "8K"
        height >= 2160 -> "4K (${height}p)" to "4K"
        height >= 1440 -> "2K (${height}p)" to "2K"
        height >= 1080 -> "Full HD (${height}p)" to "FHD"
        height >= 720 -> "HD (${height}p)" to "HD"
        height >= 480 -> "SD (${height}p)" to "SD"
        else -> "${height}p" to "${height}p"
    }

    fun parseMediaInfoJson(
        rawUrl: String,
        rawJson: String,
        canTogglePlaylist: Boolean = false,
        playlistMode: String = "auto",
    ): JSONObject {
        val cleanedUrl = validateUrl(rawUrl)
        var info = JSONObject(rawJson)
        if (info.optString("_type") == "playlist") {
            val entries = info.optJSONArray("entries")
            val wantsPlaylist = shouldExtractPlaylist(cleanedUrl, playlistMode)
            var nonNullCount = 0
            if (entries != null) {
                for (i in 0 until entries.length()) {
                    if (entries.optJSONObject(i) != null) nonNullCount++
                }
            }
            if (wantsPlaylist && (playlistMode == "playlist" || nonNullCount > 1 || !canTogglePlaylist)) {
                return parsePlaylistInfoJson(cleanedUrl, info, canTogglePlaylist)
            }
            var first: JSONObject? = null
            if (entries != null) {
                for (i in 0 until entries.length()) {
                    val candidate = entries.optJSONObject(i)
                    if (candidate != null) {
                        first = candidate
                        break
                    }
                }
            }
            info = first ?: throw IllegalArgumentException("La lista no contiene elementos disponibles.")
        }

        val durationDouble = optPositiveDouble(info, "duration")
        val durationInt = durationDouble?.roundToInt()

        val formats = info.optJSONArray("formats") ?: JSONArray()
        var bestAudioSize: Long? = null
        var bestAudioAbr = 0.0
        var bestAudioCodec: String? = null

        val byHeight = linkedMapOf<Int, MutableList<JSONObject>>()
        val fallbackVideos = mutableListOf<JSONObject>()

        for (i in 0 until formats.length()) {
            val fmt = formats.optJSONObject(i) ?: continue
            val vcodec = optNonEmptyString(fmt, "vcodec")
            val acodec = optNonEmptyString(fmt, "acodec")

            if (vcodec == "none" && acodec != null && acodec != "none") {
                val abr = optPositiveDouble(fmt, "abr") ?: optPositiveDouble(fmt, "tbr") ?: 0.0
                if (abr >= bestAudioAbr) {
                    bestAudioAbr = abr
                    bestAudioCodec = cleanAcodec(acodec)
                }
                val est = estimateStreamBytes(fmt, durationDouble)
                if (est != null && (bestAudioSize == null || est > bestAudioSize)) {
                    bestAudioSize = est
                }
            }
        }

        for (i in 0 until formats.length()) {
            val fmt = formats.optJSONObject(i) ?: continue
            val ext = fmt.optString("ext", "").lowercase(Locale.ROOT)
            val note = fmt.optString("format_note", "").lowercase(Locale.ROOT)
            val vcodec = optNonEmptyString(fmt, "vcodec")
            val acodec = optNonEmptyString(fmt, "acodec")
            val heightVal = optPositiveDouble(fmt, "height")?.toInt()

            if (ext == "mhtml" || "storyboard" in note || vcodec == "none") continue
            if (vcodec == null && acodec != null && acodec != "none" && heightVal == null) continue

            if (heightVal != null && heightVal > 0) {
                byHeight.getOrPut(heightVal) { mutableListOf() }.add(fmt)
            } else {
                fallbackVideos.add(fmt)
            }
        }

        val videoOptions = JSONArray()
        val sortedHeights = byHeight.keys.sortedDescending()
        for (height in sortedHeights) {
            val candidates = byHeight[height] ?: continue
            val best = candidates.maxWithOrNull(
                compareBy<JSONObject>(
                    { (optPositiveDouble(it, "fps") ?: 0.0).roundToInt() },
                    { codecPreference(optNonEmptyString(it, "vcodec")) },
                    { optPositiveDouble(it, "tbr") ?: 0.0 },
                    {
                        val ac = optNonEmptyString(it, "acodec")
                        if (ac != null && ac != "none") 1 else 0
                    },
                )
            ) ?: continue

            val ac = optNonEmptyString(best, "acodec")
            val hasAudio = ac != null && ac != "none"
            var estSize = estimateStreamBytes(best, durationDouble)
            if (estSize != null && !hasAudio && bestAudioSize != null) {
                estSize += bestAudioSize
            }
            val fps = optPositiveDouble(best, "fps")?.roundToInt()
            val width = optPositiveDouble(best, "width")?.roundToInt()
            val tbr = (optPositiveDouble(best, "tbr") ?: optPositiveDouble(best, "vbr"))?.roundToInt()
            val (label, tag) = resolutionLabels(height)

            videoOptions.put(
                JSONObject().apply {
                    put("id", "h-$height")
                    put("height", height)
                    put("width", width ?: JSONObject.NULL)
                    put("label", label)
                    put("quality_tag", tag)
                    put("fps", fps ?: JSONObject.NULL)
                    put("vcodec", cleanVcodec(optNonEmptyString(best, "vcodec")) ?: JSONObject.NULL)
                    put("dynamic_range", cleanDynamicRange(optNonEmptyString(best, "dynamic_range")) ?: JSONObject.NULL)
                    put("tbr", tbr ?: JSONObject.NULL)
                    put("filesize_approx", estSize ?: JSONObject.NULL)
                    put("has_audio", hasAudio)
                }
            )
        }

        if (videoOptions.length() == 0 && fallbackVideos.isNotEmpty()) {
            val best = fallbackVideos.maxByOrNull { optPositiveDouble(it, "tbr") ?: 0.0 }!!
            val ac = optNonEmptyString(best, "acodec")
            val hasAudio = ac != null && ac != "none"
            var estSize = estimateStreamBytes(best, durationDouble)
            if (estSize != null && !hasAudio && bestAudioSize != null) {
                estSize += bestAudioSize
            }
            val tbr = (optPositiveDouble(best, "tbr") ?: optPositiveDouble(best, "vbr"))?.roundToInt()
            videoOptions.put(
                JSONObject().apply {
                    put("id", "best")
                    put("height", JSONObject.NULL)
                    put("width", JSONObject.NULL)
                    put("label", "Mejor calidad disponible")
                    put("quality_tag", "MAX")
                    put("fps", JSONObject.NULL)
                    put("vcodec", cleanVcodec(optNonEmptyString(best, "vcodec")) ?: JSONObject.NULL)
                    put("dynamic_range", cleanDynamicRange(optNonEmptyString(best, "dynamic_range")) ?: JSONObject.NULL)
                    put("tbr", tbr ?: JSONObject.NULL)
                    put("filesize_approx", estSize ?: JSONObject.NULL)
                    put("has_audio", hasAudio)
                }
            )
        }

        if (videoOptions.length() == 0 && optNonEmptyString(info, "url") != null) {
            val ext = info.optString("ext", "").lowercase(Locale.ROOT)
            if (ext !in setOf("mp3", "m4a", "opus", "ogg", "wav", "flac", "aac")) {
                videoOptions.put(
                    JSONObject().apply {
                        put("id", "best")
                        put("height", JSONObject.NULL)
                        put("width", JSONObject.NULL)
                        put("label", "Mejor calidad disponible")
                        put("quality_tag", "MAX")
                        put("filesize_approx", estimateStreamBytes(info, durationDouble) ?: JSONObject.NULL)
                        put("has_audio", true)
                    }
                )
            }
        }

        val videoContainers = JSONArray().apply {
            put(JSONObject().put("value", "mp4").put("label", "MP4").put("description", "Máxima compatibilidad"))
            put(JSONObject().put("value", "mkv").put("label", "MKV").put("description", "Contenedor universal sin recodificar"))
            put(JSONObject().put("value", "webm").put("label", "WebM").put("description", "Formato ligero web"))
        }

        val audioFormats = JSONArray().apply {
            put(JSONObject().put("format", "mp3").put("label", "MP3").put("description", "Universal, funciona en cualquier reproductor").put("lossless", false))
            put(JSONObject().put("format", "m4a").put("label", "M4A (AAC)").put("description", "Mejor calidad por bitrate, ideal para móvil").put("lossless", false))
            put(JSONObject().put("format", "opus").put("label", "Opus").put("description", "Máxima eficiencia y fidelidad moderna").put("lossless", false))
            put(JSONObject().put("format", "flac").put("label", "FLAC").put("description", "Sin pérdida comprimido (archivos grandes)").put("lossless", true))
            put(JSONObject().put("format", "wav").put("label", "WAV").put("description", "Audio PCM sin compresión para edición").put("lossless", true))
        }

        val audioBitrates = JSONArray()
        for (br in AUDIO_BITRATES) {
            val est = if (durationDouble != null && durationDouble > 0) (br * 1000.0 / 8.0 * durationDouble).toLong() else null
            audioBitrates.put(
                JSONObject().apply {
                    put("bitrate", br)
                    put("label", "$br kbps")
                    put("estimated_bytes", est ?: JSONObject.NULL)
                }
            )
        }

        val subtitleLanguages = JSONArray()
        val subsObj = info.optJSONObject("subtitles")
        if (subsObj != null) {
            val keys = mutableListOf<String>()
            val iter = subsObj.keys()
            while (iter.hasNext()) {
                keys.add(iter.next())
            }
            keys.sorted().forEach { subtitleLanguages.put(it) }
        }

        val rawDesc = optNonEmptyString(info, "description")
        val trimmedDesc = if (rawDesc != null && rawDesc.length > 700) "${rawDesc.substring(0, 700).trimEnd()}…" else rawDesc

        val extractor = optNonEmptyString(info, "extractor_key") ?: optNonEmptyString(info, "extractor")
        val platform = formatPlatform(extractor)

        val viewCount = if (info.has("view_count") && !info.isNull("view_count")) info.optLong("view_count", -1L).takeIf { it >= 0 } else null
        val likeCount = if (info.has("like_count") && !info.isNull("like_count")) info.optLong("like_count", -1L).takeIf { it >= 0 } else null

        val uploader = optNonEmptyString(info, "uploader")
            ?: optNonEmptyString(info, "channel")
            ?: optNonEmptyString(info, "creator")

        return JSONObject().apply {
            put("url", cleanedUrl)
            put("title", optNonEmptyString(info, "title") ?: "Archivo multimedia")
            put("uploader", uploader ?: JSONObject.NULL)
            put("duration", durationInt ?: JSONObject.NULL)
            put("duration_text", formatDuration(durationDouble) ?: JSONObject.NULL)
            put("upload_date", formatUploadDate(optNonEmptyString(info, "upload_date")) ?: JSONObject.NULL)
            put("like_count", likeCount ?: JSONObject.NULL)
            put("description", trimmedDesc ?: JSONObject.NULL)
            put("webpage_url", optNonEmptyString(info, "webpage_url") ?: cleanedUrl)
            put("thumbnail", optNonEmptyString(info, "thumbnail") ?: JSONObject.NULL)
            put("platform", platform)
            put("view_count", viewCount ?: JSONObject.NULL)
            put("video_options", videoOptions)
            put("video_containers", videoContainers)
            put("audio_formats", audioFormats)
            put("audio_bitrates", audioBitrates)
            put("source_audio_abr", if (bestAudioAbr > 0) bestAudioAbr.roundToInt() else JSONObject.NULL)
            put("source_audio_codec", bestAudioCodec ?: JSONObject.NULL)
            put("subtitle_languages", subtitleLanguages)
            put("is_live", info.optBoolean("is_live", false))
            put("is_playlist", false)
            put("playlist_title", JSONObject.NULL)
            put("playlist_count", 0)
            put("playlist_entries", JSONArray())
            put("can_toggle_playlist", canTogglePlaylist)
        }
    }

    private fun extractEntryThumbnail(obj: JSONObject): String? {
        optNonEmptyString(obj, "thumbnail")?.let { return it }
        val thumbs = obj.optJSONArray("thumbnails") ?: return null
        for (i in thumbs.length() - 1 downTo 0) {
            val item = thumbs.optJSONObject(i) ?: continue
            optNonEmptyString(item, "url")?.let { return it }
        }
        return null
    }

    private fun normalizeEntryUrl(entry: JSONObject): String? {
        val raw = optNonEmptyString(entry, "webpage_url") ?: optNonEmptyString(entry, "url")
        if (raw != null) {
            if (raw.startsWith("http://") || raw.startsWith("https://")) return raw
            if (YOUTUBE_ID_REGEX.matches(raw)) return "https://www.youtube.com/watch?v=$raw"
        }
        val entryId = optNonEmptyString(entry, "id")
        if (entryId != null && YOUTUBE_ID_REGEX.matches(entryId)) {
            return "https://www.youtube.com/watch?v=$entryId"
        }
        return null
    }

    private fun parsePlaylistInfoJson(
        cleanedUrl: String,
        info: JSONObject,
        canTogglePlaylist: Boolean,
    ): JSONObject {
        val rawEntries = info.optJSONArray("entries") ?: JSONArray()
        val playlistEntries = JSONArray()
        var totalDuration = 0
        var hasDuration = false
        var firstThumb: String? = null
        var firstUploader: String? = null

        for (i in 0 until rawEntries.length()) {
            val entry = rawEntries.optJSONObject(i) ?: continue
            val rawTitle = optNonEmptyString(entry, "title").orEmpty()
            if (rawTitle in setOf("[Private video]", "[Deleted video]", "[Unavailable video]")) {
                continue
            }
            val oneBased = i + 1
            val durDouble = optPositiveDouble(entry, "duration")
            val durInt = durDouble?.roundToInt()
            if (durInt != null) {
                totalDuration += durInt
                hasDuration = true
            }
            val thumb = extractEntryThumbnail(entry)
            if (firstThumb == null && thumb != null) firstThumb = thumb
            val uploader = optNonEmptyString(entry, "uploader")
                ?: optNonEmptyString(entry, "channel")
                ?: optNonEmptyString(entry, "creator")
            if (firstUploader == null && uploader != null) firstUploader = uploader

            playlistEntries.put(
                JSONObject().apply {
                    put("index", oneBased)
                    put("id", optNonEmptyString(entry, "id") ?: JSONObject.NULL)
                    put("title", rawTitle.ifEmpty { "Elemento $oneBased" })
                    put("duration", durInt ?: JSONObject.NULL)
                    put("duration_text", formatDuration(durDouble) ?: JSONObject.NULL)
                    put("uploader", uploader ?: JSONObject.NULL)
                    put("thumbnail", thumb ?: JSONObject.NULL)
                    put("url", normalizeEntryUrl(entry) ?: JSONObject.NULL)
                }
            )
        }

        if (playlistEntries.length() == 0) {
            throw IllegalArgumentException("La lista no contiene elementos disponibles.")
        }

        val playlistTitle = optNonEmptyString(info, "title") ?: "Playlist"
        val playlistThumb = extractEntryThumbnail(info) ?: firstThumb
        val playlistUploader = optNonEmptyString(info, "uploader")
            ?: optNonEmptyString(info, "channel")
            ?: optNonEmptyString(info, "creator")
            ?: firstUploader

        val videoOptions = JSONArray()
        for (height in PLAYLIST_TARGET_HEIGHTS) {
            val (label, tag) = resolutionLabels(height)
            videoOptions.put(
                JSONObject().apply {
                    put("id", "h-$height")
                    put("height", height)
                    put("width", JSONObject.NULL)
                    put("label", "Hasta $label")
                    put("quality_tag", tag)
                    put("fps", JSONObject.NULL)
                    put("vcodec", JSONObject.NULL)
                    put("dynamic_range", JSONObject.NULL)
                    put("tbr", JSONObject.NULL)
                    put("filesize_approx", JSONObject.NULL)
                    put("has_audio", false)
                }
            )
        }

        val videoContainers = JSONArray().apply {
            put(JSONObject().put("value", "mp4").put("label", "MP4").put("description", "Máxima compatibilidad"))
            put(JSONObject().put("value", "mkv").put("label", "MKV").put("description", "Contenedor universal sin recodificar"))
            put(JSONObject().put("value", "webm").put("label", "WebM").put("description", "Formato ligero web"))
        }

        val audioFormats = JSONArray().apply {
            put(JSONObject().put("format", "mp3").put("label", "MP3").put("description", "Universal, funciona en cualquier reproductor").put("lossless", false))
            put(JSONObject().put("format", "m4a").put("label", "M4A (AAC)").put("description", "Mejor calidad por bitrate, ideal para móvil").put("lossless", false))
            put(JSONObject().put("format", "opus").put("label", "Opus").put("description", "Máxima eficiencia y fidelidad moderna").put("lossless", false))
            put(JSONObject().put("format", "flac").put("label", "FLAC").put("description", "Sin pérdida comprimido (archivos grandes)").put("lossless", true))
            put(JSONObject().put("format", "wav").put("label", "WAV").put("description", "Audio PCM sin compresión para edición").put("lossless", true))
        }

        val audioBitrates = JSONArray()
        for (br in AUDIO_BITRATES) {
            audioBitrates.put(
                JSONObject().apply {
                    put("bitrate", br)
                    put("label", "$br kbps")
                    put("estimated_bytes", JSONObject.NULL)
                }
            )
        }

        val extractor = optNonEmptyString(info, "extractor_key") ?: optNonEmptyString(info, "extractor")
        return JSONObject().apply {
            put("url", cleanedUrl)
            put("title", playlistTitle)
            put("uploader", playlistUploader ?: JSONObject.NULL)
            put("duration", if (hasDuration) totalDuration else JSONObject.NULL)
            put("duration_text", if (hasDuration) formatDuration(totalDuration.toDouble()) else JSONObject.NULL)
            put("upload_date", formatUploadDate(optNonEmptyString(info, "upload_date")) ?: JSONObject.NULL)
            put("like_count", JSONObject.NULL)
            put("description", optNonEmptyString(info, "description") ?: JSONObject.NULL)
            put("webpage_url", optNonEmptyString(info, "webpage_url") ?: cleanedUrl)
            put("thumbnail", playlistThumb ?: JSONObject.NULL)
            put("platform", formatPlatform(extractor))
            put("view_count", JSONObject.NULL)
            put("video_options", videoOptions)
            put("video_containers", videoContainers)
            put("audio_formats", audioFormats)
            put("audio_bitrates", audioBitrates)
            put("source_audio_abr", JSONObject.NULL)
            put("source_audio_codec", JSONObject.NULL)
            put("subtitle_languages", JSONArray())
            put("is_live", false)
            put("is_playlist", true)
            put("playlist_title", playlistTitle)
            put("playlist_count", playlistEntries.length())
            put("playlist_entries", playlistEntries)
            put("can_toggle_playlist", canTogglePlaylist)
        }
    }

    private fun formatPlatform(extractorKey: String?): String {
        if (extractorKey.isNullOrBlank()) return "Web"
        val key = extractorKey.lowercase(Locale.ROOT)
        PLATFORM_LABELS[key]?.let { return it }
        for ((prefix, label) in PLATFORM_LABELS) {
            if (key.startsWith(prefix)) return label
        }
        return extractorKey
    }

    fun buildVideoFormatSelector(height: Int?, container: String): String {
        val lower = container.lowercase(Locale.ROOT)
        if (height != null) {
            return when (lower) {
                "mp4" -> (
                    "bestvideo[height=$height][vcodec^=avc1]+bestaudio[ext=m4a]/" +
                        "bestvideo[height=$height][ext=mp4]+bestaudio[ext=m4a]/" +
                        "bestvideo[height=$height]+bestaudio[ext=m4a]/" +
                        "bestvideo[height=$height]+bestaudio/" +
                        "bestvideo[height<=$height]+bestaudio/" +
                        "best[height<=$height]/best"
                    )
                "webm" -> (
                    "bestvideo[height=$height][ext=webm]+bestaudio[ext=webm]/" +
                        "bestvideo[height=$height]+bestaudio/" +
                        "bestvideo[height<=$height]+bestaudio/" +
                        "best[height<=$height]/best"
                    )
                else -> (
                    "bestvideo[height=$height]+bestaudio/" +
                        "bestvideo[height<=$height]+bestaudio/" +
                        "best[height<=$height]/best"
                    )
            }
        }
        return when (lower) {
            "mp4" -> "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            "webm" -> "bestvideo[ext=webm]+bestaudio[ext=webm]/bestvideo+bestaudio/best"
            else -> "bestvideo+bestaudio/best"
        }
    }

    fun translateYtDlpError(raw: String?): String {
        val text = raw?.trim().orEmpty()
        val lower = text.lowercase(Locale.ROOT)
        return when {
            "unsupported url" in lower -> "Este enlace o plataforma no es compatible por el momento."
            "private video" in lower || "this video is private" in lower -> "Este video es privado y no se puede descargar sin acceso."
            "drm" in lower || "widevine" in lower -> "Este contenido está protegido con DRM y no se puede descargar."
            "sign in to confirm" in lower || "login required" in lower || "not a bot" in lower ->
                "La plataforma pidió inicio de sesión o verificación anti-bot para este enlace."
            "age" in lower && ("sign in" in lower || "verify" in lower) ->
                "El video tiene restricción de edad."
            "video unavailable" in lower || "this content isn't available" in lower || "not available" in lower ->
                "El contenido no está disponible, fue eliminado o está bloqueado en tu región."
            "timed out" in lower || "timeout" in lower -> "La conexión tardó demasiado tiempo. Intenta nuevamente."
            "http error 429" in lower || "too many requests" in lower ->
                "La plataforma limitó temporalmente las solicitudes (HTTP 429). Intenta en unos minutos."
            else -> text.removePrefix("ERROR:").trim().ifEmpty {
                "Ocurrió un error inesperado al procesar el enlace."
            }
        }
    }

    fun parseSemver(tag: String?): List<Int> {
        if (tag.isNullOrBlank()) return listOf(0)
        val nums = SEMVER_DIGITS.findAll(tag).mapNotNull { it.value.toIntOrNull() }.toList()
        return nums.ifEmpty { listOf(0) }
    }

    fun compareSemver(a: List<Int>, b: List<Int>): Int {
        val maxLen = max(a.size, b.size)
        for (i in 0 until maxLen) {
            val va = if (i < a.size) a[i] else 0
            val vb = if (i < b.size) b[i] else 0
            if (va > vb) return 1
            if (va < vb) return -1
        }
        return 0
    }

    fun pickAndroidApkAsset(assets: JSONArray, supportedAbis: Array<String>): JSONObject? {
        val apks = mutableListOf<JSONObject>()
        for (i in 0 until assets.length()) {
            val asset = assets.optJSONObject(i) ?: continue
            val name = asset.optString("name", "").lowercase(Locale.ROOT)
            if (name.endsWith(".apk")) {
                apks.add(asset)
            }
        }
        if (apks.isEmpty()) return null

        for (abi in supportedAbis) {
            val tokens = when (abi.lowercase(Locale.ROOT)) {
                "arm64-v8a" -> listOf("arm64-v8a", "arm64")
                "armeabi-v7a" -> listOf("armeabi-v7a", "armeabi", "armv7")
                "x86_64" -> listOf("x86_64", "amd64")
                else -> listOf(abi.lowercase(Locale.ROOT))
            }
            val matched = apks.firstOrNull { asset ->
                val n = asset.optString("name", "").lowercase(Locale.ROOT)
                tokens.any { tok -> tok in n }
            }
            if (matched != null) return matched
        }

        return apks.firstOrNull { "universal" in it.optString("name", "").lowercase(Locale.ROOT) }
            ?: apks.first()
    }
}
