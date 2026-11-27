import AVFoundation
import Foundation
import Network

final class MediaLibraryManager {
    static let audioExts: Set<String> = ["mp3", "m4a", "flac", "wav", "opus", "ogg", "aac"]
    static let videoExts: Set<String> = ["mp4", "mkv", "webm", "mov", "m4v"]
    static let mediaExts: Set<String> = audioExts.union(videoExts)

    private static let mimeByExt: [String: String] = [
        "mp3": "audio/mpeg",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "wav": "audio/wav",
        "opus": "audio/opus",
        "ogg": "audio/ogg",
        "mp4": "video/mp4",
        "m4v": "video/mp4",
        "mkv": "video/x-matroska",
        "webm": "video/webm",
        "mov": "video/quicktime",
    ]

    private let lock = NSLock()
    private var metadataCache: [String: [String: Any]] = [:]

    private func documentsRootDir() -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? DownloadManagerEngine.documentsDownloadDir()
    }

    private func importedDir() -> URL {
        let dir = DownloadManagerEngine.documentsDownloadDir().appendingPathComponent("Importados", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func coversDir() -> URL {
        let dir = DownloadManagerEngine.documentsDownloadDir().appendingPathComponent(".covers", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func playlistsFileURL() -> URL {
        DownloadManagerEngine.documentsDownloadDir().appendingPathComponent(".playlists.json")
    }

    private func stableHashKey(_ text: String) -> String {
        var h1: UInt64 = 14695981039346656037
        for b in text.utf8 {
            h1 ^= UInt64(b)
            h1 = h1 &* 1099511628211
        }
        return String(format: "%016llx", h1)
    }

    private func sidecarCoverURL(for path: String) -> URL? {
        let key = stableHashKey(path)
        for ext in ["jpg", "png"] {
            let u = coversDir().appendingPathComponent("\(key).\(ext)")
            if FileManager.default.fileExists(atPath: u.path) { return u }
        }
        return nil
    }

    private func saveSidecarCover(for path: String, data: Data, mime: String) {
        let key = stableHashKey(path)
        let fm = FileManager.default
        try? fm.removeItem(at: coversDir().appendingPathComponent("\(key).jpg"))
        try? fm.removeItem(at: coversDir().appendingPathComponent("\(key).png"))
        let ext = mime.lowercased().contains("png") ? "png" : "jpg"
        try? data.write(to: coversDir().appendingPathComponent("\(key).\(ext)"))
    }

    private func sidecarMetaURL(for path: String) -> URL {
        coversDir().appendingPathComponent("\(stableHashKey(path)).meta.json")
    }

    private func saveSidecarTags(for path: String, dict: [String: String]) {
        if let data = try? JSONSerialization.data(withJSONObject: dict) {
            try? data.write(to: sidecarMetaURL(for: path))
        }
    }

    private func loadSidecarTags(for path: String) -> [String: String] {
        guard let data = try? Data(contentsOf: sidecarMetaURL(for: path)),
              let parsed = (try? JSONSerialization.jsonObject(with: data)) as? [String: String] else {
            return [:]
        }
        return parsed
    }

    func scanLibrary() -> [[String: Any]] {
        let root = documentsRootDir()
        var items: [[String: Any]] = []
        collectMedia(in: root, root: root, depth: 0, maxDepth: 4, into: &items)
        items.sort { (($0["mtime"] as? Double) ?? 0.0) > (($1["mtime"] as? Double) ?? 0.0) }
        return items
    }

    private func collectMedia(in dir: URL, root: URL, depth: Int, maxDepth: Int, into items: inout [[String: Any]]) {
        let fm = FileManager.default
        guard let children = try? fm.contentsOfDirectory(
            at: dir,
            includingPropertiesForKeys: [.isDirectoryKey, .isRegularFileKey, .fileSizeKey, .contentModificationDateKey]
        ) else { return }

        for entry in children {
            let name = entry.lastPathComponent
            if name.hasPrefix(".") || name.contains(".tagging_tmp") { continue }
            let vals = try? entry.resourceValues(forKeys: [.isDirectoryKey, .isRegularFileKey, .fileSizeKey, .contentModificationDateKey])
            if vals?.isDirectory == true {
                if depth < maxDepth {
                    collectMedia(in: entry, root: root, depth: depth + 1, maxDepth: maxDepth, into: &items)
                }
            } else if vals?.isRegularFile == true {
                let ext = entry.pathExtension.lowercased()
                guard Self.mediaExts.contains(ext) else { continue }
                let relPath = dir.path.replacingOccurrences(of: root.path, with: "").trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                let folderPath = relPath.isEmpty ? "Archivos" : relPath
                let group = dir.path == root.path ? nil : dir.lastPathComponent
                let source: String
                if folderPath.contains("Importados") { source = "imported" }
                else if folderPath.contains("!Download") { source = "downloaded" }
                else { source = "device" }
                let size = Int64(vals?.fileSize ?? 0)
                let mtime = vals?.contentModificationDate?.timeIntervalSince1970 ?? 0.0
                items.append(buildItemDict(url: entry, ext: ext, size: size, mtime: mtime, source: source, folderPath: folderPath, folderGroup: group))
            }
        }
    }

    func resolveAllowedFile(_ pathStr: String) -> URL? {
        guard !pathStr.isEmpty else { return nil }
        let root = documentsRootDir().standardizedFileURL
        let target = URL(fileURLWithPath: pathStr).standardizedFileURL
        guard target.path == root.path || target.path.hasPrefix(root.path + "/") else { return nil }
        guard FileManager.default.fileExists(atPath: target.path) else { return nil }
        let ext = target.pathExtension.lowercased()
        guard Self.mediaExts.contains(ext) else { return nil }
        return target
    }

    func saveImportedFile(filename: String, data: Data) throws -> [String: Any] {
        guard !data.isEmpty else {
            throw MediaValidationError.message("El archivo está vacío.")
        }
        guard data.count <= 250 * 1024 * 1024 else {
            throw MediaValidationError.message("El archivo supera el límite permitido de 250 MB.")
        }
        let baseName = (filename.isEmpty ? "pista.mp3" : (filename as NSString).lastPathComponent)
        let cleaned = baseName.replacingOccurrences(of: #"[<>:"/\\|?*\x00-\x1F]"#, with: "_", options: .regularExpression)
        let ext = (cleaned as NSString).pathExtension.lowercased()
        guard Self.mediaExts.contains(ext) else {
            throw MediaValidationError.message("Formato no compatible (.\(ext)).")
        }

        let dir = importedDir()
        let fm = FileManager.default
        var target = dir.appendingPathComponent(cleaned)
        if fm.fileExists(atPath: target.path) {
            let stem = (cleaned as NSString).deletingPathExtension
            var counter = 1
            while fm.fileExists(atPath: target.path) {
                target = dir.appendingPathComponent("\(stem) (\(counter)).\(ext)")
                counter += 1
            }
        }
        try data.write(to: target)
        let attrs = try? fm.attributesOfItem(atPath: target.path)
        let size = (attrs?[.size] as? NSNumber)?.int64Value ?? Int64(data.count)
        let mtime = (attrs?[.modificationDate] as? Date)?.timeIntervalSince1970 ?? Date().timeIntervalSince1970
        return buildItemDict(url: target, ext: ext, size: size, mtime: mtime, source: "imported", folderPath: "!Download/Importados", folderGroup: "Importados")
    }

    func streamMedia(path: String, rangeHeader: String?, conn: NWConnection) -> Bool {
        guard let fileURL = resolveAllowedFile(path),
              let handle = try? FileHandle(forReadingFrom: fileURL) else {
            return false
        }
        defer { try? handle.close() }

        let attrs = try? FileManager.default.attributesOfItem(atPath: fileURL.path)
        let totalSize = (attrs?[.size] as? NSNumber)?.int64Value ?? 0
        guard totalSize > 0 else { return false }

        let ext = fileURL.pathExtension.lowercased()
        let mime = Self.mimeByExt[ext] ?? "application/octet-stream"

        var start: Int64 = 0
        var end: Int64 = min(totalSize - 1, 2 * 1024 * 1024 - 1)
        var isPartial = false

        if let rangeHeader, rangeHeader.lowercased().hasPrefix("bytes=") {
            isPartial = true
            let spec = rangeHeader.dropFirst(6).split(separator: ",").first.map(String.init) ?? ""
            let parts = spec.split(separator: "-", omittingEmptySubsequences: false).map(String.init)
            if parts.count == 2 {
                let sStr = parts[0].trimmingCharacters(in: .whitespaces)
                let eStr = parts[1].trimmingCharacters(in: .whitespaces)
                if sStr.isEmpty, let suffix = Int64(eStr) {
                    start = max(0, totalSize - suffix)
                    end = totalSize - 1
                } else {
                    start = min(max(0, Int64(sStr) ?? 0), totalSize - 1)
                    if let parsedEnd = Int64(eStr) {
                        end = min(max(start, parsedEnd), totalSize - 1)
                    } else {
                        end = min(start + 2 * 1024 * 1024 - 1, totalSize - 1)
                    }
                }
            }
        } else {
            end = totalSize - 1
        }

        let length = Int(max(0, end - start + 1))
        try? handle.seek(toOffset: UInt64(start))
        let chunk = (try? handle.read(upToCount: length)) ?? Data()

        let status = isPartial ? "206 Partial Content" : "200 OK"
        var header = "HTTP/1.1 \(status)\r\n"
        header += "Content-Type: \(mime)\r\n"
        header += "Accept-Ranges: bytes\r\n"
        header += "Content-Length: \(chunk.count)\r\n"
        if isPartial {
            header += "Content-Range: bytes \(start)-\(start + Int64(chunk.count) - 1)/\(totalSize)\r\n"
        }
        header += "X-Content-Type-Options: nosniff\r\nConnection: close\r\n\r\n"

        var payload = Data(header.utf8)
        payload.append(chunk)
        conn.send(content: payload, contentContext: .finalMessage, isComplete: true, completion: .contentProcessed { _ in
            conn.cancel()
        })
        return true
    }

    func extractCover(path: String) -> (Data, String)? {
        guard let fileURL = resolveAllowedFile(path) else { return nil }
        if let sidecar = sidecarCoverURL(for: fileURL.path), let data = try? Data(contentsOf: sidecar) {
            let mime = sidecar.pathExtension == "png" ? "image/png" : "image/jpeg"
            return (data, mime)
        }
        let asset = AVURLAsset(url: fileURL)
        for item in asset.commonMetadata {
            if item.commonKey == .commonKeyArtwork, let data = item.dataValue, !data.isEmpty {
                let isPng = data.starts(with: [0x89, 0x50, 0x4E, 0x47])
                return (data, isPng ? "image/png" : "image/jpeg")
            }
        }
        let parent = fileURL.deletingLastPathComponent()
        for cname in ["cover.jpg", "folder.jpg", "front.jpg", "album.jpg", "cover.png", "folder.png"] {
            let cURL = parent.appendingPathComponent(cname)
            if let data = try? Data(contentsOf: cURL), !data.isEmpty {
                return (data, cname.hasSuffix(".png") ? "image/png" : "image/jpeg")
            }
        }
        return nil
    }

    func cleanTrackQuery(_ raw: String) -> String {
        var text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.contains(".") {
            let stem = (text as NSString).deletingPathExtension
            if !stem.isEmpty { text = stem }
        }
        text = text.replacingOccurrences(of: #"^\s*\d{1,3}\s*[-._)]\s*"#, with: "", options: .regularExpression)
        text = text.replacingOccurrences(
            of: #"(\(|\[)\s*(official\s*(music\s*)?video|official\s*audio|lyric(s)?(\s*video)?|visualizer|audio|video\s*oficial|letra|hd|4k|hq|explicit|remastered(\s*\d{4})?|feat\.?[^\)\]]*)\s*(\)|\])"#,
            with: " ",
            options: [.regularExpression, .caseInsensitive]
        )
        text = text.replacingOccurrences(of: "_", with: " ")
        text = text.replacingOccurrences(of: #"\s{2,}"#, with: " ", options: .regularExpression)
        return text.trimmingCharacters(in: CharacterSet(charactersIn: " -–—|"))
    }

    func lookupMetadataOnline(query: String, limit: Int = 6) -> [[String: Any]] {
        let cleaned = cleanTrackQuery(query)
        guard !cleaned.isEmpty,
              let encoded = cleaned.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "https://itunes.apple.com/search?term=\(encoded)&media=music&entity=song&limit=\(min(12, max(1, limit)))") else {
            return []
        }

        var req = URLRequest(url: url, timeoutInterval: 10)
        req.setValue("!Download-Metadata/1.6.1", forHTTPHeaderField: "User-Agent")

        let sem = DispatchSemaphore(value: 0)
        var out: [[String: Any]] = []
        URLSession.shared.dataTask(with: req) { data, response, _ in
            defer { sem.signal() }
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard (200...299).contains(code), let data,
                  let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  let results = root["results"] as? [[String: Any]] else { return }

            for item in results {
                let title = (item["trackName"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
                let artist = (item["artistName"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
                if title.isEmpty && artist.isEmpty { continue }
                var art = ((item["artworkUrl100"] as? String) ?? (item["artworkUrl60"] as? String) ?? "").trimmingCharacters(in: .whitespaces)
                if !art.isEmpty {
                    art = art.replacingOccurrences(of: #"\d+x\d+bb\."#, with: "600x600bb.", options: .regularExpression)
                }
                let relDate = (item["releaseDate"] as? String) ?? ""
                let year = relDate.range(of: #"\d{4}"#, options: .regularExpression).map { String(relDate[$0]) } ?? ""
                let trackNum = item["trackNumber"] as? Int
                let trackCount = item["trackCount"] as? Int
                let trackStr: String
                if let tn = trackNum, let tc = trackCount { trackStr = "\(tn)/\(tc)" }
                else if let tn = trackNum { trackStr = "\(tn)" }
                else { trackStr = "" }
                let durMs = item["trackTimeMillis"] as? Double

                out.append([
                    "title": title,
                    "artist": artist,
                    "album": (item["collectionName"] as? String)?.trimmingCharacters(in: .whitespaces) ?? "",
                    "year": year,
                    "genre": (item["primaryGenreName"] as? String)?.trimmingCharacters(in: .whitespaces) ?? "",
                    "track": trackStr,
                    "cover_url": art,
                    "duration": durMs.map { $0 / 1000.0 } ?? NSNull(),
                ])
            }
        }.resume()
        sem.wait()
        return out
    }

    func applyMetadata(_ req: [String: Any]) throws -> [String: Any] {
        let pathStr = (req["path"] as? String) ?? ""
        guard let fileURL = resolveAllowedFile(pathStr) else {
            throw MediaValidationError.message("Archivo no encontrado o fuera de permisos.")
        }
        let ext = fileURL.pathExtension.lowercased()
        guard Self.audioExts.contains(ext) else {
            throw MediaValidationError.message("Solo se pueden editar metadatos en archivos de audio.")
        }

        let title = req["title"] as? String
        let artist = req["artist"] as? String
        let album = req["album"] as? String
        let year = req["year"] as? String
        let genre = req["genre"] as? String
        let track = req["track"] as? String
        let coverUrl = req["cover_url"] as? String
        let coverBase64 = req["cover_base64"] as? String
        let cover = try fetchCoverData(coverUrl: coverUrl, coverBase64: coverBase64)

        if let cover {
            saveSidecarCover(for: fileURL.path, data: cover.0, mime: cover.1)
        }
        saveSidecarTags(for: fileURL.path, dict: [
            "title": title ?? "",
            "artist": artist ?? "",
            "album": album ?? "",
            "year": year ?? "",
            "genre": genre ?? "",
            "track": track ?? "",
        ])

        let tmpOut = fileURL.deletingLastPathComponent().appendingPathComponent("\(fileURL.deletingPathExtension().lastPathComponent).tagging_tmp.\(ext)")
        let fm = FileManager.default
        defer { try? fm.removeItem(at: tmpOut) }

        if ext == "mp3" {
            try writeId3v2Mp3(
                srcURL: fileURL,
                dstURL: tmpOut,
                title: title,
                artist: artist,
                album: album,
                year: year,
                genre: genre,
                track: track,
                cover: cover
            )
            _ = try fm.replaceItemAt(fileURL, withItemAt: tmpOut)
        } else if ext == "m4a" || ext == "aac" {
            let asset = AVURLAsset(url: fileURL)
            guard let session = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetPassthrough) else {
                throw MediaValidationError.message("No se pudo iniciar la exportación de metadatos M4A.")
            }
            var items: [AVMutableMetadataItem] = []
            func addMeta(_ key: AVMetadataKey, _ value: String?) {
                guard let v = value?.trimmingCharacters(in: .whitespaces), !v.isEmpty else { return }
                let item = AVMutableMetadataItem()
                item.keySpace = .common
                item.key = key as NSString
                item.value = v as NSString
                items.append(item)
            }
            addMeta(.commonKeyTitle, title)
            addMeta(.commonKeyArtist, artist)
            addMeta(.commonKeyAlbumName, album)
            addMeta(.commonKeyCreationDate, year)
            addMeta(.commonKeyType, genre)
            if let cover {
                let artItem = AVMutableMetadataItem()
                artItem.keySpace = .common
                artItem.key = AVMetadataKey.commonKeyArtwork as NSString
                artItem.value = cover.0 as NSData
                items.append(artItem)
            }
            session.metadata = items
            session.outputURL = tmpOut
            session.outputFileType = .m4a
            let sem = DispatchSemaphore(value: 0)
            session.exportAsynchronously { sem.signal() }
            sem.wait()
            if session.status == .completed {
                _ = try fm.replaceItemAt(fileURL, withItemAt: tmpOut)
            }
        }

        lock.lock()
        metadataCache.removeValue(forKey: fileURL.path)
        lock.unlock()

        let attrs = try? fm.attributesOfItem(atPath: fileURL.path)
        let size = (attrs?[.size] as? NSNumber)?.int64Value ?? 0
        let mtime = (attrs?[.modificationDate] as? Date)?.timeIntervalSince1970 ?? Date().timeIntervalSince1970
        let relParent = fileURL.deletingLastPathComponent().lastPathComponent
        let source = relParent == "Importados" ? "imported" : "downloaded"
        return buildItemDict(url: fileURL, ext: ext, size: size, mtime: mtime, source: source, folderPath: relParent, folderGroup: relParent)
    }

    func listPlaylists() -> [[String: Any]] {
        lock.lock()
        defer { lock.unlock() }
        return loadPlaylistsUnsafe()
    }

    func createPlaylist(_ req: [String: Any]) throws -> [String: Any] {
        let name = ((req["name"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else {
            throw MediaValidationError.message("Escribe un nombre para la lista.")
        }
        let rawKind = (req["kind"] as? String) ?? "mixed"
        let kind = ["audio", "video", "mixed"].contains(rawKind) ? rawKind : "mixed"
        let items = (req["items"] as? [String]) ?? []
        let now = Date().timeIntervalSince1970
        let entry: [String: Any] = [
            "id": String(UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(10)).lowercased(),
            "name": String(name.prefix(80)),
            "kind": kind,
            "items": items,
            "created_at": now,
            "updated_at": now,
        ]
        lock.lock()
        var all = loadPlaylistsUnsafe()
        all.insert(entry, at: 0)
        savePlaylistsUnsafe(all)
        lock.unlock()
        return entry
    }

    func updatePlaylist(id: String, req: [String: Any]) throws -> [String: Any]? {
        lock.lock()
        defer { lock.unlock() }
        var all = loadPlaylistsUnsafe()
        for i in all.indices {
            if (all[i]["id"] as? String) == id {
                if let name = req["name"] as? String {
                    let cleaned = name.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !cleaned.isEmpty else {
                        throw MediaValidationError.message("El nombre de la lista no puede estar vacío.")
                    }
                    all[i]["name"] = String(cleaned.prefix(80))
                }
                if let kind = req["kind"] as? String, ["audio", "video", "mixed"].contains(kind) {
                    all[i]["kind"] = kind
                }
                if let items = req["items"] as? [String] {
                    all[i]["items"] = items
                }
                all[i]["updated_at"] = Date().timeIntervalSince1970
                savePlaylistsUnsafe(all)
                return all[i]
            }
        }
        return nil
    }

    func deletePlaylist(id: String) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        let all = loadPlaylistsUnsafe()
        let filtered = all.filter { ($0["id"] as? String) != id }
        guard filtered.count != all.count else { return false }
        savePlaylistsUnsafe(filtered)
        return true
    }

    private func loadPlaylistsUnsafe() -> [[String: Any]] {
        let url = playlistsFileURL()
        guard let data = try? Data(contentsOf: url),
              let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let pls = root["playlists"] as? [[String: Any]] else {
            return []
        }
        return pls
    }

    private func savePlaylistsUnsafe(_ pls: [[String: Any]]) {
        let data = try? JSONSerialization.data(withJSONObject: ["playlists": pls], options: [.prettyPrinted])
        if let data {
            try? data.write(to: playlistsFileURL())
        }
    }

    private func fetchCoverData(coverUrl: String?, coverBase64: String?) throws -> (Data, String)? {
        if let coverBase64, !coverBase64.trimmingCharacters(in: .whitespaces).isEmpty {
            var raw = coverBase64.trimmingCharacters(in: .whitespaces)
            var mime = "image/jpeg"
            if raw.hasPrefix("data:"), let comma = raw.firstIndex(of: ",") {
                let header = raw[..<comma].lowercased()
                if header.contains("png") { mime = "image/png" }
                raw = String(raw[raw.index(after: comma)...])
            }
            guard let data = Data(base64Encoded: raw, options: .ignoreUnknownCharacters),
                  !data.isEmpty, data.count <= 5 * 1024 * 1024 else {
                throw MediaValidationError.message("La imagen de carátula no es válida o supera 5 MB.")
            }
            return (data, mime)
        }
        if let coverUrl, !coverUrl.trimmingCharacters(in: .whitespaces).isEmpty {
            let valid = try MediaParser.validateUrl(coverUrl)
            guard let url = URL(string: valid) else {
                throw MediaValidationError.message("URL de carátula inválida.")
            }
            let sem = DispatchSemaphore(value: 0)
            var result: (Data, String)?
            var req = URLRequest(url: url, timeoutInterval: 10)
            req.setValue("!Download-Cover/1.6.1", forHTTPHeaderField: "User-Agent")
            URLSession.shared.dataTask(with: req) { data, response, _ in
                defer { sem.signal() }
                let http = response as? HTTPURLResponse
                let ctype = http?.value(forHTTPHeaderField: "Content-Type")?.split(separator: ";").first.map { String($0).lowercased() } ?? ""
                if let data, (200...299).contains(http?.statusCode ?? 0), ctype.hasPrefix("image/"), data.count <= 5 * 1024 * 1024 {
                    result = (data, ctype)
                }
            }.resume()
            sem.wait()
            guard let result else {
                throw MediaValidationError.message("No se pudo descargar la imagen de carátula.")
            }
            return result
        }
        return nil
    }

    private func writeId3v2Mp3(
        srcURL: URL,
        dstURL: URL,
        title: String?,
        artist: String?,
        album: String?,
        year: String?,
        genre: String?,
        track: String?,
        cover: (Data, String)?
    ) throws {
        let raw = try Data(contentsOf: srcURL)
        var audioOffset = 0
        if raw.count >= 10, raw[0] == 0x49, raw[1] == 0x44, raw[2] == 0x33 {
            let tagSize = ((Int(raw[6]) & 0x7F) << 21) |
                ((Int(raw[7]) & 0x7F) << 14) |
                ((Int(raw[8]) & 0x7F) << 7) |
                (Int(raw[9]) & 0x7F)
            let hasFooter = (raw[5] & 0x10) != 0
            audioOffset = min(raw.count, 10 + tagSize + (hasFooter ? 10 : 0))
        }

        var frames = Data()
        func appendFrame(id: String, payload: Data) {
            frames.append(contentsOf: id.utf8.prefix(4))
            var beSize = UInt32(payload.count).bigEndian
            withUnsafeBytes(of: &beSize) { frames.append(contentsOf: $0) }
            frames.append(contentsOf: [0x00, 0x00])
            frames.append(payload)
        }
        func addText(_ id: String, _ val: String?) {
            guard let cleaned = val?.trimmingCharacters(in: .whitespaces), !cleaned.isEmpty else { return }
            guard let utf16 = cleaned.data(using: .utf16) else { return }
            var payload = Data([0x01])
            payload.append(utf16)
            appendFrame(id: id, payload: payload)
        }

        addText("TIT2", title)
        addText("TPE1", artist)
        addText("TALB", album)
        addText("TYER", year)
        addText("TCON", genre)
        addText("TRCK", track)

        if let (img, mime) = cover {
            var apic = Data([0x00])
            apic.append(contentsOf: mime.utf8)
            apic.append(contentsOf: [0x00, 0x03, 0x00])
            apic.append(img)
            appendFrame(id: "APIC", payload: apic)
        }

        let sz = frames.count
        let syncSafe: [UInt8] = [
            UInt8((sz >> 21) & 0x7F),
            UInt8((sz >> 14) & 0x7F),
            UInt8((sz >> 7) & 0x7F),
            UInt8(sz & 0x7F),
        ]
        var output = Data([0x49, 0x44, 0x33, 0x03, 0x00, 0x00])
        output.append(contentsOf: syncSafe)
        output.append(frames)
        output.append(raw.subdata(in: audioOffset..<raw.count))
        try output.write(to: dstURL)
    }

    private func buildItemDict(
        url: URL,
        ext: String,
        size: Int64,
        mtime: Double,
        source: String,
        folderPath: String,
        folderGroup: String?
    ) -> [String: Any] {
        lock.lock()
        if let cached = metadataCache[url.path], (cached["_mtime_key"] as? Int64) == Int64(mtime) {
            lock.unlock()
            return cached
        }
        lock.unlock()

        let kind = Self.audioExts.contains(ext) ? "audio" : "video"
        let sideTags = loadSidecarTags(for: url.path)
        var title = sideTags["title"]?.isEmpty == false ? sideTags["title"]! : url.deletingPathExtension().lastPathComponent
        var artist = sideTags["artist"] ?? ""
        var album = sideTags["album"] ?? ""
        var year = sideTags["year"] ?? ""
        var genre = sideTags["genre"] ?? ""
        let track = sideTags["track"] ?? ""
        var hasCover = sidecarCoverURL(for: url.path) != nil

        let asset = AVURLAsset(url: url)
        let durationSec = CMTimeGetSeconds(asset.duration)
        let duration: Any = (durationSec.isFinite && durationSec > 0) ? durationSec : NSNull()

        for item in asset.commonMetadata {
            switch item.commonKey {
            case .commonKeyTitle:
                if (sideTags["title"] ?? "").isEmpty,
                   let v = item.stringValue?.trimmingCharacters(in: .whitespaces), !v.isEmpty { title = v }
            case .commonKeyArtist:
                if artist.isEmpty { artist = item.stringValue?.trimmingCharacters(in: .whitespaces) ?? artist }
            case .commonKeyAlbumName:
                if album.isEmpty { album = item.stringValue?.trimmingCharacters(in: .whitespaces) ?? album }
            case .commonKeyCreationDate:
                if year.isEmpty, let v = item.stringValue, let yRange = v.range(of: #"\d{4}"#, options: .regularExpression) {
                    year = String(v[yRange])
                }
            case .commonKeyType:
                if genre.isEmpty { genre = item.stringValue?.trimmingCharacters(in: .whitespaces) ?? genre }
            case .commonKeyArtwork:
                if let data = item.dataValue, !data.isEmpty { hasCover = true }
            default:
                break
            }
        }

        if !hasCover {
            let parent = url.deletingLastPathComponent()
            for cname in ["cover.jpg", "folder.jpg", "front.jpg", "album.jpg", "cover.png", "folder.png"] {
                if FileManager.default.fileExists(atPath: parent.appendingPathComponent(cname).path) {
                    hasCover = true
                    break
                }
            }
        }

        let itemDict: [String: Any] = [
            "path": url.path,
            "filename": url.lastPathComponent,
            "title": title,
            "artist": artist,
            "album": album,
            "year": year,
            "genre": genre,
            "track": track,
            "kind": kind,
            "ext": ext.uppercased(),
            "mime": Self.mimeByExt[ext] ?? "application/octet-stream",
            "duration": duration,
            "bitrate": NSNull(),
            "codec": ext.uppercased(),
            "size": size,
            "mtime": mtime,
            "has_cover": hasCover,
            "source": source,
            "folder_path": folderPath,
            "folder_group": folderGroup ?? NSNull(),
            "_mtime_key": Int64(mtime),
        ]

        lock.lock()
        if metadataCache.count > 256 { metadataCache.removeAll() }
        metadataCache[url.path] = itemDict
        lock.unlock()
        return itemDict
    }
}
