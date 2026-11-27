import Foundation

enum MediaValidationError: LocalizedError {
    case message(String)

    var errorDescription: String? {
        switch self {
        case .message(let text):
            return text
        }
    }
}

enum MediaParser {
    private static let blockedHosts: Set<String> = ["localhost", "localhost.localdomain"]
    private static let monthsEs: [Int: String] = [
        1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
        7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
    ]
    private static let platformLabels: [String: String] = [
        "youtube": "YouTube",
        "youtubetab": "YouTube",
        "tiktok": "TikTok",
        "instagram": "Instagram",
        "twitter": "X / Twitter",
        "x": "X / Twitter",
        "reddit": "Reddit",
        "twitch": "Twitch",
        "vimeo": "Vimeo",
        "soundcloud": "SoundCloud",
        "facebook": "Facebook",
        "dailymotion": "Dailymotion",
        "bilibili": "Bilibili",
        "bandcamp": "Bandcamp",
        "generic": "Enlace directo",
    ]
    private static let audioBitrates = [320, 256, 192, 128, 96]
    private static let playlistTargetHeights = [2160, 1440, 1080, 720, 480, 360]

    static func urlHasVideoAndList(_ rawUrl: String) -> Bool {
        guard let components = URLComponents(string: rawUrl.trimmingCharacters(in: .whitespacesAndNewlines)),
              let items = components.queryItems else {
            return false
        }
        let hasList = items.contains { $0.name == "list" && !($0.value ?? "").isEmpty }
        guard hasList else { return false }
        let hasVideo = items.contains { $0.name == "v" && !($0.value ?? "").isEmpty }
        let hasWatch = components.path.lowercased().contains("/watch")
        return hasVideo || hasWatch
    }

    static func shouldExtractPlaylist(_ rawUrl: String, playlistMode: String = "auto") -> Bool {
        let mode = playlistMode.lowercased()
        if mode == "single" { return false }
        if mode == "playlist" { return true }
        if urlHasVideoAndList(rawUrl),
           let components = URLComponents(string: rawUrl.trimmingCharacters(in: .whitespacesAndNewlines)),
           let listVal = components.queryItems?.first(where: { $0.name == "list" })?.value,
           listVal.uppercased().hasPrefix("RD") {
            return false
        }
        return true
    }

    static func sanitizeFolderName(_ name: String?, fallback: String = "Playlist") -> String {
        let raw = (name ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let forbidden = CharacterSet(charactersIn: "<>:\"/\\|?*")
        var cleaned = raw.unicodeScalars.map { scalar -> String in
            if forbidden.contains(scalar) || scalar.value < 32 {
                return "_"
            }
            return String(scalar)
        }.joined()
        while cleaned.contains("  ") {
            cleaned = cleaned.replacingOccurrences(of: "  ", with: " ")
        }
        cleaned = cleaned.trimmingCharacters(in: CharacterSet(charactersIn: " ."))
        if cleaned.isEmpty { return fallback }
        if cleaned.count > 90 {
            cleaned = String(cleaned.prefix(90)).trimmingCharacters(in: CharacterSet(charactersIn: " ."))
        }
        return cleaned.isEmpty ? fallback : cleaned
    }

    static func validateUrl(_ rawUrl: String) throws -> String {
        let cleaned = rawUrl.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned.isEmpty {
            throw MediaValidationError.message("Por favor, introduce una URL.")
        }
        if cleaned.contains("\r") || cleaned.contains("\n") || cleaned.contains("\u{0}") {
            throw MediaValidationError.message("La URL contiene caracteres no válidos.")
        }
        guard let components = URLComponents(string: cleaned),
              let scheme = components.scheme?.lowercased(),
              scheme == "http" || scheme == "https" else {
            throw MediaValidationError.message("La URL debe comenzar por http:// o https://.")
        }
        guard let rawHost = components.host, !rawHost.isEmpty else {
            throw MediaValidationError.message("La URL no tiene un dominio válido.")
        }
        let host = rawHost.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        if blockedHosts.contains(host) || host.hasSuffix(".local") || host.hasSuffix(".internal") {
            throw MediaValidationError.message("No se permiten direcciones locales o internas.")
        }
        let literal = host.trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        if isPrivateOrLoopbackIP(literal) {
            throw MediaValidationError.message("No se permiten direcciones IP privadas o locales.")
        }
        return cleaned
    }

    private static func isPrivateOrLoopbackIP(_ host: String) -> Bool {
        let parts = host.split(separator: ".", omittingEmptySubsequences: false)
        if parts.count == 4, let o0 = Int(parts[0]), let o1 = Int(parts[1]),
           let o2 = Int(parts[2]), let o3 = Int(parts[3]),
           (0...255).contains(o0), (0...255).contains(o1),
           (0...255).contains(o2), (0...255).contains(o3) {
            if o0 == 10 || o0 == 127 || o0 == 0 { return true }
            if o0 == 169 && o1 == 254 { return true }
            if o0 == 172 && (16...31).contains(o1) { return true }
            if o0 == 192 && o1 == 168 { return true }
            if (224...255).contains(o0) { return true }
            return false
        }
        if host.contains(":") {
            let lower = host.lowercased()
            if lower == "::1" || lower == "::" || lower.hasPrefix("fe80:") || lower.hasPrefix("fc") || lower.hasPrefix("fd") {
                return true
            }
        }
        return false
    }

    static func formatDuration(_ seconds: Double?) -> String? {
        guard let seconds, seconds >= 0 else { return nil }
        let total = max(0, Int(seconds.rounded()))
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let secs = total % 60
        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, secs)
        }
        return String(format: "%d:%02d", minutes, secs)
    }

    static func formatUploadDate(_ raw: String?) -> String? {
        guard let raw, raw.count == 8, raw.allSatisfy({ $0.isNumber }) else { return nil }
        let y = String(raw.prefix(4))
        let mIdx = raw.index(raw.startIndex, offsetBy: 4)
        let dIdx = raw.index(raw.startIndex, offsetBy: 6)
        guard let m = Int(raw[mIdx..<dIdx]), let d = Int(raw[dIdx...]), let label = monthsEs[m] else {
            return nil
        }
        return "\(d) \(label) \(y)"
    }

    private static func positiveDouble(_ dict: [String: Any], _ key: String) -> Double? {
        guard let raw = dict[key], !(raw is NSNull) else { return nil }
        if let n = raw as? Double, n > 0 { return n }
        if let n = raw as? Int, n > 0 { return Double(n) }
        if let n = raw as? NSNumber, n.doubleValue > 0 { return n.doubleValue }
        return nil
    }

    private static func nonEmptyString(_ dict: [String: Any], _ key: String) -> String? {
        guard let str = dict[key] as? String else { return nil }
        let trimmed = str.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func estimateStreamBytes(_ fmt: [String: Any], duration: Double?) -> Int64? {
        if let size = positiveDouble(fmt, "filesize") ?? positiveDouble(fmt, "filesize_approx") {
            return Int64(size)
        }
        if let tbr = positiveDouble(fmt, "tbr") ?? positiveDouble(fmt, "vbr") ?? positiveDouble(fmt, "abr"),
           let duration, duration > 0 {
            return Int64(tbr * duration * 1000.0 / 8.0)
        }
        return nil
    }

    private static func cleanVcodec(_ vcodec: String?) -> String? {
        guard let vcodec, !vcodec.isEmpty, vcodec != "none" else { return nil }
        let lower = vcodec.lowercased()
        if lower.hasPrefix("avc") || lower.contains("h264") { return "H.264" }
        if lower.hasPrefix("vp09") || lower.hasPrefix("vp9") { return "VP9" }
        if lower.hasPrefix("av01") || lower.hasPrefix("av1") { return "AV1" }
        if lower.hasPrefix("hev") || lower.hasPrefix("hvc") || lower.contains("h265") { return "HEVC" }
        return vcodec.split(separator: ".").first.map { String($0).uppercased() }
    }

    private static func cleanAcodec(_ acodec: String?) -> String? {
        guard let acodec, !acodec.isEmpty, acodec != "none" else { return nil }
        let lower = acodec.lowercased()
        if lower.hasPrefix("mp4a") || lower.contains("aac") { return "AAC" }
        if lower.contains("opus") { return "Opus" }
        if lower.contains("vorbis") { return "Vorbis" }
        if lower.contains("mp3") { return "MP3" }
        if lower.contains("flac") { return "FLAC" }
        return acodec.split(separator: ".").first.map { String($0).uppercased() }
    }

    private static func cleanDynamicRange(_ dr: String?) -> String? {
        guard let dr else { return nil }
        let cleaned = dr.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        if cleaned.isEmpty || cleaned == "SDR" || cleaned == "NONE" { return nil }
        if cleaned.contains("HDR") || cleaned.contains("HLG") || cleaned.contains("DV") || cleaned.contains("PQ") {
            return "HDR"
        }
        return cleaned
    }

    private static func codecPreference(_ vcodec: String?) -> Int {
        guard let vcodec, !vcodec.isEmpty, vcodec != "none" else { return 0 }
        let lower = vcodec.lowercased()
        if lower.hasPrefix("avc") || lower.contains("h264") { return 3 }
        if lower.hasPrefix("hev") || lower.hasPrefix("hvc") || lower.contains("h265") { return 2 }
        if lower.hasPrefix("vp09") || lower.hasPrefix("vp9") { return 1 }
        return 0
    }

    private static func resolutionLabels(_ height: Int) -> (String, String) {
        if height >= 4320 { return ("8K (\(height)p)", "8K") }
        if height >= 2160 { return ("4K (\(height)p)", "4K") }
        if height >= 1440 { return ("2K (\(height)p)", "2K") }
        if height >= 1080 { return ("Full HD (\(height)p)", "FHD") }
        if height >= 720 { return ("HD (\(height)p)", "HD") }
        if height >= 480 { return ("SD (\(height)p)", "SD") }
        return ("\(height)p", "\(height)p")
    }

    static func parseMediaInfoJson(
        rawUrl: String,
        rawJson: String,
        canTogglePlaylist: Bool = false,
        playlistMode: String = "auto"
    ) throws -> [String: Any] {
        let cleanedUrl = try validateUrl(rawUrl)
        guard let data = rawJson.data(using: .utf8),
              var info = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw MediaValidationError.message("No se pudo interpretar la respuesta del enlace.")
        }

        if (info["_type"] as? String) == "playlist" {
            let entries = (info["entries"] as? [Any])?.compactMap { $0 as? [String: Any] } ?? []
            let wantsPlaylist = shouldExtractPlaylist(cleanedUrl, playlistMode: playlistMode)
            if wantsPlaylist && (playlistMode.lowercased() == "playlist" || entries.count > 1 || !canTogglePlaylist) {
                return try parsePlaylistInfoJson(cleanedUrl: cleanedUrl, info: info, canTogglePlaylist: canTogglePlaylist)
            }
            guard let first = entries.first else {
                throw MediaValidationError.message("La lista no contiene elementos disponibles.")
            }
            info = first
        }

        let durationDouble = positiveDouble(info, "duration")
        let durationInt = durationDouble.map { Int($0.rounded()) }
        let formats = info["formats"] as? [[String: Any]] ?? []

        var bestAudioSize: Int64?
        var bestAudioAbr = 0.0
        var bestAudioCodec: String?

        var byHeight: [Int: [[String: Any]]] = [:]
        var fallbackVideos: [[String: Any]] = []

        for fmt in formats {
            let vcodec = nonEmptyString(fmt, "vcodec")
            let acodec = nonEmptyString(fmt, "acodec")
            if vcodec == "none", let ac = acodec, ac != "none" {
                let abr = positiveDouble(fmt, "abr") ?? positiveDouble(fmt, "tbr") ?? 0.0
                if abr >= bestAudioAbr {
                    bestAudioAbr = abr
                    bestAudioCodec = cleanAcodec(ac)
                }
                if let est = estimateStreamBytes(fmt, duration: durationDouble) {
                    if bestAudioSize == nil || est > bestAudioSize! {
                        bestAudioSize = est
                    }
                }
            }
        }

        for fmt in formats {
            let ext = (nonEmptyString(fmt, "ext") ?? "").lowercased()
            let note = (nonEmptyString(fmt, "format_note") ?? "").lowercased()
            let vcodec = nonEmptyString(fmt, "vcodec")
            let acodec = nonEmptyString(fmt, "acodec")
            let heightVal = positiveDouble(fmt, "height").map { Int($0) }

            if ext == "mhtml" || note.contains("storyboard") || vcodec == "none" { continue }
            if vcodec == nil && acodec != nil && acodec != "none" && heightVal == nil { continue }

            if let h = heightVal, h > 0 {
                byHeight[h, default: []].append(fmt)
            } else {
                fallbackVideos.append(fmt)
            }
        }

        var videoOptions: [[String: Any]] = []
        for height in byHeight.keys.sorted(by: >) {
            guard let candidates = byHeight[height], !candidates.isEmpty else { continue }
            let best = candidates.max { a, b in
                let aMp4 = (nonEmptyString(a, "ext")?.lowercased() == "mp4") ? 1 : 0
                let bMp4 = (nonEmptyString(b, "ext")?.lowercased() == "mp4") ? 1 : 0
                if aMp4 != bMp4 { return aMp4 < bMp4 }
                let aPref = codecPreference(nonEmptyString(a, "vcodec"))
                let bPref = codecPreference(nonEmptyString(b, "vcodec"))
                if aPref != bPref { return aPref < bPref }
                let aFps = Int((positiveDouble(a, "fps") ?? 0).rounded())
                let bFps = Int((positiveDouble(b, "fps") ?? 0).rounded())
                if aFps != bFps { return aFps < bFps }
                return (positiveDouble(a, "tbr") ?? 0) < (positiveDouble(b, "tbr") ?? 0)
            }!

            let ac = nonEmptyString(best, "acodec")
            let hasAudio = ac != nil && ac != "none"
            var estSize = estimateStreamBytes(best, duration: durationDouble)
            if let s = estSize, !hasAudio, let aSize = bestAudioSize {
                estSize = s + aSize
            }
            let fps = positiveDouble(best, "fps").map { Int($0.rounded()) }
            let width = positiveDouble(best, "width").map { Int($0.rounded()) }
            let tbr = (positiveDouble(best, "tbr") ?? positiveDouble(best, "vbr")).map { Int($0.rounded()) }
            let (label, tag) = resolutionLabels(height)

            videoOptions.append([
                "id": "h-\(height)",
                "height": height,
                "width": width ?? NSNull(),
                "label": label,
                "quality_tag": tag,
                "fps": fps ?? NSNull(),
                "vcodec": cleanVcodec(nonEmptyString(best, "vcodec")) ?? NSNull(),
                "dynamic_range": cleanDynamicRange(nonEmptyString(best, "dynamic_range")) ?? NSNull(),
                "tbr": tbr ?? NSNull(),
                "filesize_approx": estSize ?? NSNull(),
                "has_audio": hasAudio,
            ])
        }

        if videoOptions.isEmpty, let best = fallbackVideos.max(by: {
            (positiveDouble($0, "tbr") ?? 0) < (positiveDouble($1, "tbr") ?? 0)
        }) {
            let ac = nonEmptyString(best, "acodec")
            let hasAudio = ac != nil && ac != "none"
            var estSize = estimateStreamBytes(best, duration: durationDouble)
            if let s = estSize, !hasAudio, let aSize = bestAudioSize {
                estSize = s + aSize
            }
            videoOptions.append([
                "id": "best",
                "height": NSNull(),
                "width": NSNull(),
                "label": "Mejor calidad disponible",
                "quality_tag": "MAX",
                "fps": NSNull(),
                "vcodec": cleanVcodec(nonEmptyString(best, "vcodec")) ?? NSNull(),
                "dynamic_range": cleanDynamicRange(nonEmptyString(best, "dynamic_range")) ?? NSNull(),
                "tbr": (positiveDouble(best, "tbr") ?? positiveDouble(best, "vbr")).map { Int($0.rounded()) } ?? NSNull(),
                "filesize_approx": estSize ?? NSNull(),
                "has_audio": hasAudio,
            ])
        }

        if videoOptions.isEmpty, nonEmptyString(info, "url") != nil {
            let ext = (nonEmptyString(info, "ext") ?? "").lowercased()
            if !["mp3", "m4a", "opus", "ogg", "wav", "flac", "aac"].contains(ext) {
                videoOptions.append([
                    "id": "best",
                    "height": NSNull(),
                    "label": "Mejor calidad disponible",
                    "quality_tag": "MAX",
                    "filesize_approx": estimateStreamBytes(info, duration: durationDouble) ?? NSNull(),
                    "has_audio": true,
                ])
            }
        }

        let videoContainers: [[String: String]] = [
            ["value": "mp4", "label": "MP4", "description": "Nativo para iPhone y Fototeca"],
        ]

        let audioFormats: [[String: Any]] = [
            ["format": "m4a", "label": "M4A (AAC)", "description": "Formato nativo Apple de alta fidelidad", "lossless": false],
            ["format": "mp4", "label": "Original", "description": "Pista de audio directa sin recodificar", "lossless": true],
        ]

        let audioBitrates: [[String: Any]] = audioBitrates.map { br in
            let est: Any = (durationDouble != nil && durationDouble! > 0)
                ? Int64(Double(br) * 1000.0 / 8.0 * durationDouble!)
                : NSNull()
            return [
                "bitrate": br,
                "label": "\(br) kbps",
                "estimated_bytes": est,
            ]
        }

        let subtitlesObj = info["subtitles"] as? [String: Any] ?? [:]
        let subtitleLanguages = subtitlesObj.keys.sorted()

        var trimmedDesc: String? = nonEmptyString(info, "description")
        if let desc = trimmedDesc, desc.count > 700 {
            trimmedDesc = String(desc.prefix(700)).trimmingCharacters(in: .whitespacesAndNewlines) + "…"
        }

        let extractor = nonEmptyString(info, "extractor_key") ?? nonEmptyString(info, "extractor")
        let platform = formatPlatform(extractor)
        let uploader = nonEmptyString(info, "uploader")
            ?? nonEmptyString(info, "channel")
            ?? nonEmptyString(info, "creator")

        return [
            "url": cleanedUrl,
            "title": nonEmptyString(info, "title") ?? "Archivo multimedia",
            "uploader": uploader ?? NSNull(),
            "duration": durationInt ?? NSNull(),
            "duration_text": formatDuration(durationDouble) ?? NSNull(),
            "upload_date": formatUploadDate(nonEmptyString(info, "upload_date")) ?? NSNull(),
            "like_count": positiveDouble(info, "like_count").map { Int64($0) } ?? NSNull(),
            "description": trimmedDesc ?? NSNull(),
            "webpage_url": nonEmptyString(info, "webpage_url") ?? cleanedUrl,
            "thumbnail": nonEmptyString(info, "thumbnail") ?? NSNull(),
            "platform": platform,
            "view_count": positiveDouble(info, "view_count").map { Int64($0) } ?? NSNull(),
            "video_options": videoOptions,
            "video_containers": videoContainers,
            "audio_formats": audioFormats,
            "audio_bitrates": audioBitrates,
            "source_audio_abr": bestAudioAbr > 0 ? Int(bestAudioAbr.rounded()) : NSNull(),
            "source_audio_codec": bestAudioCodec ?? NSNull(),
            "subtitle_languages": subtitleLanguages,
            "is_live": (info["is_live"] as? Bool) ?? false,
            "is_playlist": false,
            "playlist_title": NSNull(),
            "playlist_count": 0,
            "playlist_entries": [],
            "can_toggle_playlist": canTogglePlaylist,
        ]
    }

    private static func extractEntryThumbnail(_ obj: [String: Any]) -> String? {
        if let thumb = nonEmptyString(obj, "thumbnail") { return thumb }
        if let thumbs = obj["thumbnails"] as? [[String: Any]] {
            for item in thumbs.reversed() {
                if let u = nonEmptyString(item, "url") { return u }
            }
        }
        return nil
    }

    private static func normalizeEntryUrl(_ entry: [String: Any]) -> String? {
        if let raw = nonEmptyString(entry, "webpage_url") ?? nonEmptyString(entry, "url") {
            if raw.hasPrefix("http://") || raw.hasPrefix("https://") { return raw }
            if raw.range(of: #"^[A-Za-z0-9_-]{11}$"#, options: .regularExpression) != nil {
                return "https://www.youtube.com/watch?v=\(raw)"
            }
        }
        if let entryId = nonEmptyString(entry, "id"),
           entryId.range(of: #"^[A-Za-z0-9_-]{11}$"#, options: .regularExpression) != nil {
            return "https://www.youtube.com/watch?v=\(entryId)"
        }
        return nil
    }

    private static func parsePlaylistInfoJson(
        cleanedUrl: String,
        info: [String: Any],
        canTogglePlaylist: Bool
    ) throws -> [String: Any] {
        let rawEntries = info["entries"] as? [Any] ?? []
        var playlistEntries: [[String: Any]] = []
        var totalDuration = 0
        var hasDuration = false
        var firstThumb: String?
        var firstUploader: String?

        let skipTitles: Set<String> = ["[Private video]", "[Deleted video]", "[Unavailable video]"]
        for (offset, raw) in rawEntries.enumerated() {
            guard let entry = raw as? [String: Any] else { continue }
            let rawTitle = nonEmptyString(entry, "title") ?? ""
            if skipTitles.contains(rawTitle) { continue }

            let oneBased = offset + 1
            let durDouble = positiveDouble(entry, "duration")
            let durInt = durDouble.map { Int($0.rounded()) }
            if let d = durInt {
                totalDuration += d
                hasDuration = true
            }
            let thumb = extractEntryThumbnail(entry)
            if firstThumb == nil, let thumb { firstThumb = thumb }
            let uploader = nonEmptyString(entry, "uploader")
                ?? nonEmptyString(entry, "channel")
                ?? nonEmptyString(entry, "creator")
            if firstUploader == nil, let uploader { firstUploader = uploader }

            playlistEntries.append([
                "index": oneBased,
                "id": nonEmptyString(entry, "id") ?? NSNull(),
                "title": rawTitle.isEmpty ? "Elemento \(oneBased)" : rawTitle,
                "duration": durInt ?? NSNull(),
                "duration_text": formatDuration(durDouble) ?? NSNull(),
                "uploader": uploader ?? NSNull(),
                "thumbnail": thumb ?? NSNull(),
                "url": normalizeEntryUrl(entry) ?? NSNull(),
            ])
        }

        if playlistEntries.isEmpty {
            throw MediaValidationError.message("La lista no contiene elementos disponibles.")
        }

        let playlistTitle = nonEmptyString(info, "title") ?? "Playlist"
        let playlistThumb = extractEntryThumbnail(info) ?? firstThumb
        let playlistUploader = nonEmptyString(info, "uploader")
            ?? nonEmptyString(info, "channel")
            ?? nonEmptyString(info, "creator")
            ?? firstUploader

        let videoOptions: [[String: Any]] = playlistTargetHeights.map { height in
            let (label, tag) = resolutionLabels(height)
            return [
                "id": "h-\(height)",
                "height": height,
                "width": NSNull(),
                "label": "Hasta \(label)",
                "quality_tag": tag,
                "fps": NSNull(),
                "vcodec": NSNull(),
                "dynamic_range": NSNull(),
                "tbr": NSNull(),
                "filesize_approx": NSNull(),
                "has_audio": false,
            ]
        }

        let videoContainers: [[String: String]] = [
            ["value": "mp4", "label": "MP4", "description": "Nativo para iPhone y Fototeca"],
        ]
        let audioFormats: [[String: Any]] = [
            ["format": "m4a", "label": "M4A (AAC)", "description": "Formato nativo Apple de alta fidelidad", "lossless": false],
            ["format": "mp4", "label": "Original", "description": "Pista de audio directa sin recodificar", "lossless": true],
        ]
        let bitrateOpts: [[String: Any]] = audioBitrates.map { br in
            ["bitrate": br, "label": "\(br) kbps", "estimated_bytes": NSNull()]
        }

        let extractor = nonEmptyString(info, "extractor_key") ?? nonEmptyString(info, "extractor")
        return [
            "url": cleanedUrl,
            "title": playlistTitle,
            "uploader": playlistUploader ?? NSNull(),
            "duration": hasDuration ? totalDuration : NSNull(),
            "duration_text": hasDuration ? (formatDuration(Double(totalDuration)) ?? NSNull()) : NSNull(),
            "upload_date": formatUploadDate(nonEmptyString(info, "upload_date")) ?? NSNull(),
            "like_count": NSNull(),
            "description": nonEmptyString(info, "description") ?? NSNull(),
            "webpage_url": nonEmptyString(info, "webpage_url") ?? cleanedUrl,
            "thumbnail": playlistThumb ?? NSNull(),
            "platform": formatPlatform(extractor),
            "view_count": NSNull(),
            "video_options": videoOptions,
            "video_containers": videoContainers,
            "audio_formats": audioFormats,
            "audio_bitrates": bitrateOpts,
            "source_audio_abr": NSNull(),
            "source_audio_codec": NSNull(),
            "subtitle_languages": [],
            "is_live": false,
            "is_playlist": true,
            "playlist_title": playlistTitle,
            "playlist_count": playlistEntries.count,
            "playlist_entries": playlistEntries,
            "can_toggle_playlist": canTogglePlaylist,
        ]
    }

    private static func formatPlatform(_ extractorKey: String?) -> String {
        guard let extractorKey, !extractorKey.isEmpty else { return "Web" }
        let key = extractorKey.lowercased()
        if let exact = platformLabels[key] { return exact }
        for (prefix, label) in platformLabels where key.hasPrefix(prefix) {
            return label
        }
        return extractorKey
    }

    /// Build separate video and audio selectors tailored for iOS native AVFoundation muxing,
    /// plus a muxed fallback for single-file platforms (TikTok, Instagram, X).
    static func buildVideoSelectors(height: Int?) -> (videoSelector: String, audioSelector: String, muxedFallback: String) {
        if let h = height {
            let vSel = "bestvideo[height=\(h)][vcodec^=avc1]/bestvideo[height=\(h)][ext=mp4]/bestvideo[height<=\(h)][vcodec^=avc1]/bestvideo[height<=\(h)][ext=mp4]"
            let aSel = "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio"
            let mSel = "best[height=\(h)][ext=mp4]/best[height<=\(h)][ext=mp4]/best[height<=\(h)]/best"
            return (vSel, aSel, mSel)
        }
        return (
            "bestvideo[vcodec^=avc1]/bestvideo[ext=mp4]",
            "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio",
            "best[ext=mp4]/best"
        )
    }

    static func translateYtDlpError(_ raw: String?) -> String {
        let text = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = text.lowercased()
        if lower.contains("unsupported url") { return "Este enlace o plataforma no es compatible por el momento." }
        if lower.contains("private video") || lower.contains("this video is private") {
            return "Este video es privado y no se puede descargar sin acceso."
        }
        if lower.contains("drm") || lower.contains("widevine") {
            return "Este contenido está protegido con DRM y no se puede descargar."
        }
        if lower.contains("sign in to confirm") || lower.contains("login required") || lower.contains("not a bot") {
            return "La plataforma pidió inicio de sesión o verificación anti-bot para este enlace."
        }
        if lower.contains("video unavailable") || lower.contains("not available") {
            return "El contenido no está disponible, fue eliminado o está bloqueado en tu región."
        }
        if lower.contains("timed out") || lower.contains("timeout") {
            return "La conexión tardó demasiado tiempo. Intenta nuevamente."
        }
        if lower.contains("429") || lower.contains("too many requests") {
            return "La plataforma limitó temporalmente las solicitudes (HTTP 429). Intenta en unos minutos."
        }
        let cleaned = text.replacingOccurrences(of: "ERROR:", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
        return cleaned.isEmpty ? "Ocurrió un error inesperado al procesar el enlace." : cleaned
    }

    static func parseSemver(_ tag: String?) -> [Int] {
        guard let tag, !tag.isEmpty else { return [0] }
        let parts = tag.split { !$0.isNumber }.compactMap { Int($0) }
        return parts.isEmpty ? [0] : parts
    }

    static func compareSemver(_ a: [Int], _ b: [Int]) -> Int {
        let count = max(a.count, b.count)
        for i in 0..<count {
            let va = i < a.count ? a[i] : 0
            let vb = i < b.count ? b[i] : 0
            if va > vb { return 1 }
            if va < vb { return -1 }
        }
        return 0
    }

    static func pickIOSIpaAsset(_ assets: [[String: Any]]) -> [String: Any]? {
        let ipas = assets.filter { (($0["name"] as? String) ?? "").lowercased().hasSuffix(".ipa") }
        return ipas.first { (($0["name"] as? String) ?? "").lowercased().contains("ios") } ?? ipas.first
    }
}
