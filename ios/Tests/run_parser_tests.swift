import Foundation

func expect(_ condition: Bool, _ message: String) {
    if !condition {
        fputs("TEST FAILED: \(message)\n", stderr)
        exit(1)
    }
}

@main
struct ParserTestRunner {
    static func main() {
        do {
            let cleaned = try MediaParser.validateUrl("  https://www.youtube.com/watch?v=jNQXAC9IVRw  ")
            expect(cleaned == "https://www.youtube.com/watch?v=jNQXAC9IVRw", "valid URL normalization")
        } catch {
            expect(false, "valid URL threw \(error)")
        }

        for bad in ["", "not-a-url", "file:///etc/passwd", "http://localhost:8000", "http://127.0.0.1:8000", "http://192.168.1.2/v.mp4"] {
            var didFail = false
            do {
                _ = try MediaParser.validateUrl(bad)
            } catch {
                didFail = true
            }
            expect(didFail, "invalid URL \(bad) should throw")
        }

        let rawInfo: [String: Any] = [
            "title": "Video iOS Test",
            "uploader": "Juan",
            "duration": 100.0,
            "upload_date": "20260423",
            "like_count": 500,
            "view_count": 2000,
            "extractor_key": "Youtube",
            "subtitles": ["es": [], "en": []],
            "formats": [
                ["ext": "mhtml", "format_note": "storyboard", "vcodec": "none", "height": 180],
                ["ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128, "filesize": 1_600_000],
                ["ext": "mp4", "width": 1920, "height": 1080, "fps": 60, "vcodec": "avc1.640028", "acodec": "none", "tbr": 3000, "filesize": 24_000_000],
                ["ext": "mp4", "width": 3840, "height": 2160, "fps": 60, "vcodec": "avc1.640033", "acodec": "none", "tbr": 12000, "filesize": 80_000_000, "dynamic_range": "HDR10"],
            ],
        ]
        let rawData = try! JSONSerialization.data(withJSONObject: rawInfo)
        let parsed = try! MediaParser.parseMediaInfoJson(rawUrl: "https://www.youtube.com/watch?v=test", rawJson: String(decoding: rawData, as: UTF8.self))

        expect((parsed["platform"] as? String) == "YouTube", "platform mapping")
        expect((parsed["upload_date"] as? String) == "23 abr 2026", "upload_date formatting")
        expect((parsed["source_audio_abr"] as? Int) == 128, "source audio abr")
        expect((parsed["source_audio_codec"] as? String) == "AAC", "source audio codec")

        let videoOptions = parsed["video_options"] as! [[String: Any]]
        expect(videoOptions.count == 2, "deduplicated video options")
        expect((videoOptions[0]["height"] as? Int) == 2160, "4K first")
        expect((videoOptions[0]["dynamic_range"] as? String) == "HDR", "HDR detection")
        expect((videoOptions[0]["filesize_approx"] as? Int64) == 81_600_000, "audio size added")

        let sel = MediaParser.buildVideoSelectors(height: 1080)
        expect(sel.videoSelector.contains("height=1080"), "exact height video selector")
        expect(sel.muxedFallback.contains("height=1080"), "exact height muxed fallback")

        expect(MediaParser.compareSemver(MediaParser.parseSemver("v1.3.0"), MediaParser.parseSemver("1.2.0")) > 0, "semver compare")
        let ipaPick = MediaParser.pickIOSIpaAsset([
            ["name": "Download-Setup-v1.3.0.exe"],
            ["name": "Download-v1.3.0-ios.ipa"],
        ])
        expect((ipaPick?["name"] as? String) == "Download-v1.3.0-ios.ipa", "pickIOSIpaAsset")

        print("IOS MEDIA PARSER TESTS OK")
    }
}
