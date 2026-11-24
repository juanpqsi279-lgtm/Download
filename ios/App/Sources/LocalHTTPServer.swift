import Foundation
import Network
import YTDLP

final class LocalHTTPServer {
    private let engine: DownloadManagerEngine
    private let onOpenShareSheet: (URL) -> Void
    private var listener: NWListener?
    private let queue = DispatchQueue(label: "com.juancorporation.exclaimdownload.http", qos: .userInitiated)
    private(set) var port: UInt16 = 0

    init(engine: DownloadManagerEngine, onOpenShareSheet: @escaping (URL) -> Void) {
        self.engine = engine
        self.onOpenShareSheet = onOpenShareSheet
    }

    func start() throws -> UInt16 {
        let params = NWParameters.tcp
        params.requiredLocalEndpoint = NWEndpoint.hostPort(host: .ipv4(.loopback), port: .any)
        let listener = try NWListener(using: params)
        self.listener = listener

        let readySem = DispatchSemaphore(value: 0)
        var startError: Error?

        listener.stateUpdateHandler = { [weak self] state in
            switch state {
            case .ready:
                self?.port = listener.port?.rawValue ?? 0
                readySem.signal()
            case .failed(let err):
                startError = err
                readySem.signal()
            default:
                break
            }
        }

        listener.newConnectionHandler = { [weak self] conn in
            self?.handleConnection(conn)
        }

        listener.start(queue: queue)
        readySem.wait()
        if let startError {
            throw startError
        }
        return port
    }

    func stop() {
        listener?.cancel()
        listener = nil
    }

    private func handleConnection(_ conn: NWConnection) {
        conn.start(queue: queue)
        receiveRequest(on: conn, buffer: Data())
    }

    private func receiveRequest(on conn: NWConnection, buffer: Data) {
        conn.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            if let error {
                conn.cancel()
                _ = error
                return
            }
            var acc = buffer
            if let data { acc.append(data) }

            let sep = Data("\r\n\r\n".utf8)
            if let headerRange = acc.range(of: sep) {
                let headerData = acc.subdata(in: 0..<headerRange.lowerBound)
                let bodyStart = headerRange.upperBound
                let headerText = String(decoding: headerData, as: UTF8.self)
                let lines = headerText.components(separatedBy: "\r\n")
                let firstParts = (lines.first ?? "").split(separator: " ")
                let method = firstParts.first.map { String($0).uppercased() } ?? "GET"
                let target = firstParts.count > 1 ? String(firstParts[1]) : "/"

                var contentLength = 0
                for line in lines.dropFirst() {
                    if let colon = line.firstIndex(of: ":") {
                        let k = line[..<colon].trimmingCharacters(in: .whitespaces).lowercased()
                        if k == "content-length" {
                            contentLength = Int(line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)) ?? 0
                        }
                    }
                }

                let availableBody = acc.count - bodyStart
                if availableBody >= contentLength {
                    let bodyData = contentLength > 0
                        ? acc.subdata(in: bodyStart..<(bodyStart + contentLength))
                        : Data()
                    DispatchQueue.global(qos: .userInitiated).async {
                        self.dispatch(method: method, rawTarget: target, body: bodyData, conn: conn)
                    }
                    return
                }
            }

            if isComplete {
                conn.cancel()
                return
            }
            self.receiveRequest(on: conn, buffer: acc)
        }
    }

    private func dispatch(method: String, rawTarget: String, body: Data, conn: NWConnection) {
        let qIdx = rawTarget.firstIndex(of: "?")
        let path = qIdx.map { String(rawTarget[..<$0]) } ?? rawTarget
        let query = qIdx.map { String(rawTarget[rawTarget.index(after: $0)...]) } ?? ""

        if method == "GET" && path == "/" {
            serveWebAsset("static/index.html", mime: "text/html; charset=utf-8", conn: conn)
            return
        }
        if method == "GET" && path.hasPrefix("/static/") {
            let rel = String(path.dropFirst("/static/".count))
            if rel.isEmpty || rel.contains("..") || rel.contains("\\") {
                sendJson(conn, status: 404, dict: ["detail": "No encontrado."])
                return
            }
            let mime: String
            if rel.hasSuffix(".css") { mime = "text/css; charset=utf-8" }
            else if rel.hasSuffix(".js") { mime = "application/javascript; charset=utf-8" }
            else if rel.hasSuffix(".png") { mime = "image/png" }
            else if rel.hasSuffix(".webmanifest") { mime = "application/manifest+json; charset=utf-8" }
            else if rel.hasSuffix(".html") { mime = "text/html; charset=utf-8" }
            else { mime = "application/octet-stream" }
            serveWebAsset("static/\(rel)", mime: mime, conn: conn)
            return
        }

        if method == "GET" && path == "/api/health" {
            sendJson(conn, status: 200, dict: ["status": "ok", "tools": AppUpdater.runtimeToolsJson()])
            return
        }

        if method == "GET" && path == "/api/app-info" {
            let defaults = UserDefaults.standard
            let theme = defaults.string(forKey: "exclaim_theme") ?? "dark"
            let payload: [String: Any] = [
                "name": "!Download",
                "developer": "Juan Corporation",
                "version": AppUpdater.appVersion(),
                "platform": "ios",
                "desktop_mode": true,
                "frozen": true,
                "can_self_update": false,
                "github_repo": AppUpdater.githubRepo,
                "download_dir": "Archivos/!Download",
                "settings": [
                    "theme": theme,
                    "download_dir": "Archivos/!Download",
                ],
                "tools": AppUpdater.runtimeToolsJson(),
            ]
            sendJson(conn, status: 200, dict: payload)
            return
        }

        if method == "POST" && path == "/api/settings" {
            let req = (try? JSONSerialization.jsonObject(with: body) as? [String: Any]) ?? [:]
            if let theme = req["theme"] as? String, ["dark", "light", "system"].contains(theme) {
                UserDefaults.standard.set(theme, forKey: "exclaim_theme")
            }
            let current = UserDefaults.standard.string(forKey: "exclaim_theme") ?? "dark"
            sendJson(conn, status: 200, dict: [
                "settings": ["theme": current, "download_dir": "Archivos/!Download"],
                "download_dir": "Archivos/!Download",
            ])
            return
        }

        if method == "POST" && path == "/api/info" {
            let req = (try? JSONSerialization.jsonObject(with: body) as? [String: Any]) ?? [:]
            let rawUrl = (req["url"] as? String) ?? ""
            let url: String
            do {
                url = try MediaParser.validateUrl(rawUrl)
            } catch {
                sendJson(conn, status: 400, dict: ["detail": error.localizedDescription])
                return
            }

            do {
                let out = try YTDLP.shared.run([
                    "--dump-single-json", "--no-playlist", "--playlist-items", "1",
                    "--skip-download", "--no-warnings", "--socket-timeout", "25",
                    url,
                ])
                guard out.code == 0 else {
                    sendJson(conn, status: 422, dict: ["detail": MediaParser.translateYtDlpError(out.errorMessage ?? out.stderr)])
                    return
                }
                let info = try MediaParser.parseMediaInfoJson(rawUrl: url, rawJson: out.stdout)
                sendJson(conn, status: 200, dict: info)
            } catch {
                sendJson(conn, status: 422, dict: ["detail": MediaParser.translateYtDlpError(error.localizedDescription)])
            }
            return
        }

        if method == "GET" && path == "/api/thumbnail" {
            handleThumbnail(query: query, conn: conn)
            return
        }

        if method == "POST" && path == "/api/downloads" {
            let req = (try? JSONSerialization.jsonObject(with: body) as? [String: Any]) ?? [:]
            let rawUrl = (req["url"] as? String) ?? ""
            let url: String
            do {
                url = try MediaParser.validateUrl(rawUrl)
            } catch {
                sendJson(conn, status: 400, dict: ["detail": error.localizedDescription])
                return
            }

            let height = (req["height"] as? Int) ?? (req["height"] as? NSNumber)?.intValue
            let jobReq = DownloadManagerEngine.JobRequest(
                url: url,
                mode: (req["mode"] as? String) ?? "video",
                height: height,
                container: (req["container"] as? String) ?? "mp4",
                audioFormat: (req["audio_format"] as? String) ?? "m4a",
                audioBitrate: (req["audio_bitrate"] as? Int) ?? 192,
                embedMetadata: (req["embed_metadata"] as? Bool) ?? true,
                titleHint: (req["title_hint"] as? String),
            )
            let job = engine.createJob(jobReq)
            sendJson(conn, status: 200, dict: job.toJsonDict())
            return
        }

        if method == "GET" && path == "/api/downloads" {
            let data = (try? JSONSerialization.data(withJSONObject: engine.listRecentJobs())) ?? Data("[]".utf8)
            sendBytes(conn, status: 200, mime: "application/json; charset=utf-8", data: data)
            return
        }

        if method == "GET" && path.hasPrefix("/api/downloads/") && path.hasSuffix("/events") {
            let jobId = String(path.dropFirst("/api/downloads/".count).dropLast("/events".count))
            handleSse(jobId: jobId, conn: conn)
            return
        }

        if method == "POST" && path.hasPrefix("/api/downloads/") && path.hasSuffix("/cancel") {
            let jobId = String(path.dropFirst("/api/downloads/".count).dropLast("/cancel".count))
            if let job = engine.cancelJob(jobId) {
                sendJson(conn, status: 200, dict: job)
            } else {
                sendJson(conn, status: 404, dict: ["detail": "Descarga no encontrada."])
            }
            return
        }

        if method == "GET" && path.hasPrefix("/api/downloads/") {
            let jobId = String(path.dropFirst("/api/downloads/".count))
            if let job = engine.getJob(jobId) {
                sendJson(conn, status: 200, dict: job)
            } else {
                sendJson(conn, status: 404, dict: ["detail": "Descarga no encontrada."])
            }
            return
        }

        if method == "GET" && path == "/api/updates/check" {
            sendJson(conn, status: 200, dict: AppUpdater.checkAppUpdate())
            return
        }

        if method == "POST" && path == "/api/updates/engine" {
            let versions = (try? YTDLP.shared.versions()) ?? [:]
            let ver = versions["yt_dlp"] ?? "2026.10.26"
            sendJson(conn, status: 200, dict: [
                "updated": false,
                "current_version": ver,
                "latest_version": ver,
                "restart_required": false,
                "message": "En iOS el motor yt-dlp (\(ver)) + JavaScriptCore viene integrado y se actualiza junto con la app.",
            ])
            return
        }

        if method == "POST" && path == "/api/system/open-file" {
            let req = (try? JSONSerialization.jsonObject(with: body) as? [String: Any]) ?? [:]
            let pathStr = (req["path"] as? String) ?? ""
            if let fileURL = engine.resolveSavedFile(path: pathStr) {
                DispatchQueue.main.async { self.onOpenShareSheet(fileURL) }
                sendJson(conn, status: 200, dict: ["opened": true])
            } else {
                sendJson(conn, status: 404, dict: ["detail": "Archivo no encontrado."])
            }
            return
        }

        if method == "POST" && path == "/api/system/open-folder" {
            let req = (try? JSONSerialization.jsonObject(with: body) as? [String: Any]) ?? [:]
            let pathStr = (req["path"] as? String) ?? ""
            let target = engine.resolveSavedFile(path: pathStr) ?? DownloadManagerEngine.documentsDownloadDir()
            DispatchQueue.main.async { self.onOpenShareSheet(target) }
            sendJson(conn, status: 200, dict: ["opened": true])
            return
        }

        sendJson(conn, status: 404, dict: ["detail": "Ruta no encontrada."])
    }

    private func handleThumbnail(query: String, conn: NWConnection) {
        guard let rawUrl = parseQueryParam(query, key: "url"),
              let validUrl = try? MediaParser.validateUrl(rawUrl),
              let url = URL(string: validUrl) else {
            sendJson(conn, status: 400, dict: ["detail": "URL de miniatura inválida."])
            return
        }

        var req = URLRequest(url: url, timeoutInterval: 10)
        req.setValue(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
            forHTTPHeaderField: "User-Agent"
        )
        let sem = DispatchSemaphore(value: 0)
        URLSession.shared.dataTask(with: req) { [weak self] data, response, _ in
            defer { sem.signal() }
            guard let self else { return }
            let http = response as? HTTPURLResponse
            let mime = http?.value(forHTTPHeaderField: "Content-Type")?.split(separator: ";").first.map { String($0).lowercased() } ?? ""
            guard let data, (200...299).contains(http?.statusCode ?? 0), mime.hasPrefix("image/"), data.count <= 5 * 1024 * 1024 else {
                self.sendJson(conn, status: 502, dict: ["detail": "No se pudo cargar la miniatura."])
                return
            }
            self.sendBytes(conn, status: 200, mime: mime, data: data, extraHeaders: ["Cache-Control": "public, max-age=3600"])
        }.resume()
        sem.wait()
    }

    private func handleSse(jobId: String, conn: NWConnection) {
        guard let sub = engine.subscribe(jobId: jobId, handler: { [weak conn] payload in
            let frame = Data("data: \(payload)\n\n".utf8)
            conn?.send(content: frame, completion: .contentProcessed { _ in })
        }) else {
            sendJson(conn, status: 404, dict: ["detail": "Descarga no encontrada."])
            return
        }

        let (token, initial, isTerminal) = sub
        let header = "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream; charset=utf-8\r\nCache-Control: no-cache\r\nConnection: close\r\n\r\n"
        conn.send(content: Data(header.utf8), completion: .contentProcessed { _ in })
        conn.send(content: Data("data: \(initial)\n\n".utf8), completion: .contentProcessed { _ in })

        if isTerminal {
            engine.unsubscribe(jobId: jobId, token: token)
            conn.send(content: Data(), contentContext: .finalMessage, isComplete: true, completion: .contentProcessed { _ in
                conn.cancel()
            })
            return
        }

        conn.stateUpdateHandler = { [weak self] state in
            if case .cancelled = state {
                self?.engine.unsubscribe(jobId: jobId, token: token)
            } else if case .failed = state {
                self?.engine.unsubscribe(jobId: jobId, token: token)
            }
        }
    }

    private func serveWebAsset(_ relPath: String, mime: String, conn: NWConnection) {
        guard let base = Bundle.main.resourceURL?.appendingPathComponent("WebAssets") else {
            sendJson(conn, status: 404, dict: ["detail": "WebAssets no encontrado."])
            return
        }
        let fileURL = base.appendingPathComponent(relPath)
        guard let data = try? Data(contentsOf: fileURL) else {
            sendJson(conn, status: 404, dict: ["detail": "Recurso no encontrado."])
            return
        }
        sendBytes(conn, status: 200, mime: mime, data: data)
    }

    private func sendJson(_ conn: NWConnection, status: Int, dict: [String: Any]) {
        let data = (try? JSONSerialization.data(withJSONObject: dict)) ?? Data("{}".utf8)
        sendBytes(conn, status: status, mime: "application/json; charset=utf-8", data: data)
    }

    private func sendBytes(
        _ conn: NWConnection,
        status: Int,
        mime: String,
        data: Data,
        extraHeaders: [String: String] = [:]
    ) {
        let reason: String
        switch status {
        case 200: reason = "OK"
        case 400: reason = "Bad Request"
        case 404: reason = "Not Found"
        case 422: reason = "Unprocessable Entity"
        case 502: reason = "Bad Gateway"
        default: reason = "Error"
        }
        var header = "HTTP/1.1 \(status) \(reason)\r\nContent-Type: \(mime)\r\nContent-Length: \(data.count)\r\nX-Content-Type-Options: nosniff\r\n"
        for (k, v) in extraHeaders {
            header += "\(k): \(v)\r\n"
        }
        header += "Connection: close\r\n\r\n"
        var full = Data(header.utf8)
        full.append(data)
        conn.send(content: full, contentContext: .finalMessage, isComplete: true, completion: .contentProcessed { _ in
            conn.cancel()
        })
    }

    private func parseQueryParam(_ query: String, key: String) -> String? {
        for pair in query.split(separator: "&") {
            let parts = pair.split(separator: "=", maxSplits: 1)
            if parts.count == 2 {
                let k = String(parts[0]).removingPercentEncoding ?? String(parts[0])
                if k == key {
                    return String(parts[1]).removingPercentEncoding ?? String(parts[1])
                }
            }
        }
        return nil
    }
}
