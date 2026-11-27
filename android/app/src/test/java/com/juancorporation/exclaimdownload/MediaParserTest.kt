package com.juancorporation.exclaimdownload

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MediaParserTest {

    @Test
    fun `validateUrl accepts public http and https links`() {
        val cleaned = MediaParser.validateUrl("  https://www.youtube.com/watch?v=jNQXAC9IVRw  ")
        assertEquals("https://www.youtube.com/watch?v=jNQXAC9IVRw", cleaned)
    }

    @Test
    fun `validateUrl rejects local and private addresses`() {
        val invalidUrls = listOf(
            "",
            "not-a-url",
            "file:///etc/passwd",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://192.168.1.10/video.mp4",
        )
        for (url in invalidUrls) {
            val failed = runCatching { MediaParser.validateUrl(url) }.isFailure
            assertTrue("Expected failure for $url", failed)
        }
    }

    @Test
    fun `extractFirstUrl extracts url from share sheet text`() {
        val shared = "Mira este video increíble!! https://youtu.be/jNQXAC9IVRw?si=abc123."
        assertEquals("https://youtu.be/jNQXAC9IVRw?si=abc123", MediaParser.extractFirstUrl(shared))
        assertNull(MediaParser.extractFirstUrl("Texto sin enlace"))
    }

    @Test
    fun `parseMediaInfoJson deduplicates resolutions adds audio size and extracts metadata`() {
        val raw = JSONObject().apply {
            put("title", "Video de prueba")
            put("uploader", "Juan")
            put("duration", 100.0)
            put("upload_date", "20260423")
            put("like_count", 420)
            put("view_count", 1500)
            put("extractor_key", "Youtube")
            put("subtitles", JSONObject().put("es", JSONArray()).put("en", JSONArray()))
            put(
                "formats",
                JSONArray().apply {
                    put(JSONObject().put("ext", "mhtml").put("format_note", "storyboard").put("vcodec", "none").put("height", 180))
                    put(JSONObject().put("ext", "webm").put("vcodec", "none").put("acodec", "opus").put("abr", 128).put("filesize", 1_600_000))
                    put(JSONObject().put("ext", "mp4").put("width", 1920).put("height", 1080).put("fps", 30).put("vcodec", "avc1.640028").put("acodec", "none").put("tbr", 2500).put("filesize", 20_000_000))
                    put(JSONObject().put("ext", "webm").put("width", 1920).put("height", 1080).put("fps", 60).put("vcodec", "vp09.00.41").put("acodec", "none").put("tbr", 3200).put("filesize", 24_000_000))
                    put(JSONObject().put("ext", "webm").put("width", 3840).put("height", 2160).put("fps", 60).put("vcodec", "vp09.02.51").put("acodec", "none").put("tbr", 12000).put("filesize", 80_000_000).put("dynamic_range", "HDR10"))
                },
            )
        }

        val parsed = MediaParser.parseMediaInfoJson("https://www.youtube.com/watch?v=test", raw.toString())
        assertEquals("YouTube", parsed.getString("platform"))
        assertEquals("23 abr 2026", parsed.getString("upload_date"))
        assertEquals(128, parsed.getInt("source_audio_abr"))
        assertEquals("Opus", parsed.getString("source_audio_codec"))

        val videoOptions = parsed.getJSONArray("video_options")
        assertEquals(2, videoOptions.length())

        val first = videoOptions.getJSONObject(0)
        assertEquals(2160, first.getInt("height"))
        assertEquals("HDR", first.getString("dynamic_range"))
        assertEquals(81_600_000L, first.getLong("filesize_approx"))

        val second = videoOptions.getJSONObject(1)
        assertEquals(1080, second.getInt("height"))
        assertEquals(60, second.getInt("fps"))
    }

    @Test
    fun `buildVideoFormatSelector prioritizes exact height before fallback`() {
        val sel4k = MediaParser.buildVideoFormatSelector(2160, "mp4")
        assertTrue(sel4k.indexOf("height=2160") < sel4k.indexOf("height<=2160"))
        assertTrue("bestvideo[height=2160]+bestaudio" in sel4k)
    }

    @Test
    fun `parseSemver and pickAndroidApkAsset choose matching abi`() {
        assertTrue(MediaParser.compareSemver(MediaParser.parseSemver("v1.2.0"), MediaParser.parseSemver("1.1.0")) > 0)

        val assets = JSONArray().apply {
            put(JSONObject().put("name", "Download-Setup-v1.2.0.exe"))
            put(JSONObject().put("name", "Download-v1.2.0-android-universal.apk"))
            put(JSONObject().put("name", "Download-v1.2.0-android-arm64.apk"))
        }
        val arm64Pick = MediaParser.pickAndroidApkAsset(assets, arrayOf("arm64-v8a", "armeabi-v7a"))
        assertNotNull(arm64Pick)
        assertEquals("Download-v1.2.0-android-arm64.apk", arm64Pick!!.getString("name"))

        val fallbackPick = MediaParser.pickAndroidApkAsset(assets, arrayOf("riscv64"))
        assertNotNull(fallbackPick)
        assertEquals("Download-v1.2.0-android-universal.apk", fallbackPick!!.getString("name"))
    }

    @Test
    fun `playlist detection and parsing preserve one-based indices`() {
        val videoWithMix = "https://www.youtube.com/watch?v=abc&list=RDabc"
        assertTrue(MediaParser.urlHasVideoAndList(videoWithMix))
        assertTrue(!MediaParser.shouldExtractPlaylist(videoWithMix, "auto"))
        assertTrue(MediaParser.shouldExtractPlaylist(videoWithMix, "playlist"))
        assertEquals("Mi_Lista_", MediaParser.sanitizeFolderName("  Mi:Lista/  ", "Playlist"))

        val raw = JSONObject().apply {
            put("_type", "playlist")
            put("title", "Lista Test")
            put("extractor_key", "YoutubeTab")
            put(
                "entries",
                JSONArray().apply {
                    put(JSONObject().put("id", "aaa11111111").put("title", "Uno").put("duration", 60))
                    put(JSONObject().put("id", "bbb22222222").put("title", "[Private video]"))
                    put(JSONObject().put("id", "ccc33333333").put("title", "Tres").put("duration", 120))
                },
            )
        }
        val parsed = MediaParser.parseMediaInfoJson("https://www.youtube.com/playlist?list=PL99", raw.toString())
        assertTrue(parsed.getBoolean("is_playlist"))
        assertEquals(2, parsed.getInt("playlist_count"))
        val entries = parsed.getJSONArray("playlist_entries")
        assertEquals(1, entries.getJSONObject(0).getInt("index"))
        assertEquals(3, entries.getJSONObject(1).getInt("index"))
    }
}
