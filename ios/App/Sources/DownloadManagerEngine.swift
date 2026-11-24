import Foundation
import YTDLP

final class DownloadManagerEngine {
    static let terminalStatuses: Set<String> = ["completed", "error", "cancelled"]

    struct JobRequest {
        let url: String
        let mode: String
        let height: Int?
        let container: String
        let audioFormat: String
        let audioBitrate: Int
        let embedMetadata: Bool
        let titleHint: String?
    }

    final class JobRecord {
        let jobId: String
        let req: JobRequest
        let jobDir: URL
        let qualityLabel: String
        let createdAt: Double

        var status: String = "queued"
        var stage: String = "En cola..."
        var percent: Double = 0.0
        var speed: Double?
        var eta: Int?
        var downloadedBytes: Int64?
        var totalBytes: Int64?
        var filename: String?
        var filesize: Int64?
        var savedPath: String?
        var savedFileURL: URL?
        var title: String?
        var error: String?
        var cancelled: Bool = false
        var subscribers: [(UUID, (String) -> Void)] = []

        init(jobId: String, req: JobRequest, jobDir: URL, qualityLabel: String, createdAt: Double) {
            self.jobId = jobId
            self.req = req
            self.jobDir = jobDir
            self.qualityLabel = qualityLabel
            self.title = req.titleHint
            self.createdAt = createdAt
        }

        func toJsonDict() -> [String: Any] {
            [
                "job_id": jobId,
                "status": status,
                "stage": stage,
                "percent": (percent * 10.0).rounded() / 10.0,
                "speed": speed ?? NSNull(),
                "eta": eta ?? NSNull(),
                "downloaded_bytes": downloadedBytes ?? NSNull(),
                "total_bytes": totalBytes ?? NSNull(),
                "filename": filename ?? NSNull(),
                "filesize": filesize ?? NSNull(),
                "saved_path": savedPath ?? NSNull(),
                "title": title ?? NSNull(),
                "mode": req.mode,
                "quality_label": qualityLabel,
                "error": error ?? NSNull(),
                "created_at": createdAt,
            ]
        }

        func toJsonString() -> String {
            let data = (try? JSONSerialization.data(withJSONObject: toJsonDict())) ?? Data("{}".utf8)
            return String(decoding: data, as: UTF8.self)
        }
    }

    private let lock = NSLock()
    private let queue = DispatchQueue(label: "com.juancorporation.exclaimdownload.jobs", qos: .userInitiated, attributes: .concurrent)
    private let semaphore = DispatchSemaphore(value: 2)
    private var jobs: [String: JobRecord] = [:]

    static func documentsDownloadDir() -> URL {
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        let folder = docs.appendingPathComponent("!Download", isDirectory: true)
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder
    }

    func createJob(_ req: JobRequest) -> JobRecord {
        let jobId = UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(12).lowercased()
        let tempRoot = FileManager.default.temporaryDirectory.appendingPathComponent("exclaim_jobs", isDirectory: true)
        let jobDir = tempRoot.appendingPathComponent(String(jobId), isDirectory: true)
        try? FileManager.default.createDirectory(at: jobDir, withIntermediateDirectories: true)

        let qualityLabel: String
        if req.mode == "video" {
            let res = req.height.map { "\($0)p" } ?? "Mejor"
            qualityLabel = "\(res) · \(req.container.uppercased())"
        } else if req.audioFormat == "mp4" {
            qualityLabel = "Original · Audio"
        } else {
            qualityLabel = "\(req.audioFormat.uppercased()) · \(req.audioBitrate) kbps"
        }

        let job = JobRecord(
            jobId: String(jobId),
            req: req,
            jobDir: jobDir,
            qualityLabel: qualityLabel,
            createdAt: Date().timeIntervalSince1970
        )

        lock.lock()
        jobs[job.jobId] = job
        lock.unlock()

        queue.async { [weak self] in
            self?.semaphore.wait()
            defer { self?.semaphore.signal() }
            self?.runJob(job)
        }
        return job
    }

    func getJob(_ jobId: String) -> [String: Any]? {
        lock.lock()
        defer { lock.unlock() }
        return jobs[jobId]?.toJsonDict()
    }

    func listRecentJobs(limit: Int = 15) -> [[String: Any]] {
        lock.lock()
        let sorted = jobs.values.sorted { $0.createdAt > $1.createdAt }.prefix(limit)
        let out = sorted.map { $0.toJsonDict() }
        lock.unlock()
        return out
    }

    func subscribe(jobId: String, handler: @escaping (String) -> Void) -> (UUID, String, Bool)? {
        lock.lock()
        defer { lock.unlock() }
        guard let job = jobs[jobId] else { return nil }
        let snapshot = job.toJsonString()
        let isTerminal = Self.terminalStatuses.contains(job.status)
        let token = UUID()
        if !isTerminal {
            job.subscribers.append((token, handler))
        }
        return (token, snapshot, isTerminal)
    }

    func unsubscribe(jobId: String, token: UUID) {
        lock.lock()
        jobs[jobId]?.subscribers.removeAll { $0.0 == token }
        lock.unlock()
    }

    func cancelJob(_ jobId: String) -> [String: Any]? {
        lock.lock()
        guard let job = jobs[jobId] else {
            lock.unlock()
            return nil
        }
        if Self.terminalStatuses.contains(job.status) {
            let dict = job.toJsonDict()
            lock.unlock()
            return dict
        }
        job.cancelled = true
        if job.status == "queued" {
            job.status = "cancelled"
            job.stage = "Descarga cancelada"
            try? FileManager.default.removeItem(at: job.jobDir)
        } else {
            job.stage = "Cancelando descarga..."
        }
        let dict = job.toJsonDict()
        let payload = job.toJsonString()
        let subs = job.subscribers
        if job.status == "cancelled" {
            job.subscribers.removeAll()
        }
        lock.unlock()

        subs.forEach { $0.1(payload) }
        YTDLP.shared.cancel(id: jobId)
        return dict
    }

    func resolveSavedFile(path: String) -> URL? {
        lock.lock()
        defer { lock.unlock() }
        for job in jobs.values {
            if job.savedPath == path, let url = job.savedFileURL, FileManager.default.fileExists(atPath: url.path) {
                return url
            }
        }
        return nil
    }

    private func updateJob(_ job: JobRecord, forceNotify: Bool = true, mutate: (JobRecord) -> Void) {
        lock.lock()
        mutate(job)
        let isTerminal = Self.terminalStatuses.contains(job.status)
        let payload = forceNotify || isTerminal ? job.toJsonString() : nil
        let subs = payload != nil ? job.subscribers : []
        if isTerminal {
            job.subscribers.removeAll()
        }
        lock.unlock()

        if let payload {
            subs.forEach { $0.1(payload) }
        }
    }

    private func runJob(_ job: JobRecord) {
        lock.lock()
        let wasCancelled = job.cancelled || job.status == "cancelled"
        lock.unlock()
        if wasCancelled {
            try? FileManager.default.removeItem(at: job.jobDir)
            return
        }

        updateJob(job) {
            $0.status = "downloading"
            $0.stage = "Preparando descarga..."
            $0.percent = 0.0
        }

        do {
            let finalFile: URL
            if job.req.mode == "video" {
                finalFile = try executeVideoJob(job)
            } else {
                finalFile = try executeAudioJob(job)
            }

            let savedURL = try moveUniqueToDocuments(finalFile, preferredName: finalFile.lastPathComponent)
            try? FileManager.default.removeItem(at: job.jobDir)

            let attrs = try? FileManager.default.attributesOfItem(atPath: savedURL.path)
            let size = (attrs?[.size] as? NSNumber)?.int64Value ?? 0

            updateJob(job) {
                $0.status = "completed"
                $0.stage = "¡Guardado en Archivos!"
                $0.percent = 100.0
                $0.speed = nil
                $0.eta = 0
                $0.filename = savedURL.lastPathComponent
                $0.filesize = size
                $0.savedPath = "Archivos/!Download/\(savedURL.lastPathComponent)"
                $0.savedFileURL = savedURL
            }
        } catch is CancellationError {
            try? FileManager.default.removeItem(at: job.jobDir)
            updateJob(job) {
                $0.status = "cancelled"
                $0.stage = "Descarga cancelada"
                $0.speed = nil
                $0.eta = nil
            }
        } catch {
            try? FileManager.default.removeItem(at: job.jobDir)
            updateJob(job) {
                $0.status = "error"
                $0.stage = "Error en la descarga"
                $0.speed = nil
                $0.eta = nil
                $0.error = MediaParser.translateYtDlpError(error.localizedDescription)
            }
        }
    }

    private func executeVideoJob(_ job: JobRecord) throws -> URL {
        let selectors = MediaParser.buildVideoSelectors(height: job.req.height)
        let videoDir = job.jobDir.appendingPathComponent("v", isDirectory: true)
        let audioDir = job.jobDir.appendingPathComponent("a", isDirectory: true)
        try? FileManager.default.createDirectory(at: videoDir, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: audioDir, withIntermediateDirectories: true)

        let vOut = try runYtDlp(
            job: job,
            args: [
                "--newline", "--no-playlist", "--playlist-items", "1", "--no-mtime",
                "-f", selectors.videoSelector,
                "-o", videoDir.appendingPathComponent("%(title).90B.%(ext)s").path,
                job.req.url,
            ],
            stageLabel: "Descargando pista de video..."
        )

        if vOut.code == 0, let videoFile = largestMediaFile(in: videoDir) {
            let aOut = try runYtDlp(
                job: job,
                args: [
                    "--newline", "--no-playlist", "--playlist-items", "1", "--no-mtime",
                    "-f", selectors.audioSelector,
                    "-o", audioDir.appendingPathComponent("audio.%(ext)s").path,
                    job.req.url,
                ],
                stageLabel: "Descargando pista de audio..."
            )
            if aOut.code == 0, let audioFile = largestMediaFile(in: audioDir) {
                updateJob(job) {
                    $0.status = "processing"
                    $0.stage = "Uniendo video y audio..."
                    $0.percent = 99.0
                    $0.speed = nil
                    $0.eta = 0
                }
                let baseName = videoFile.deletingPathExtension().lastPathComponent
                let mergedURL = job.jobDir.appendingPathComponent("\(baseName).mp4")
                try runAsyncBlocking {
                    try await AVMediaMuxer.muxVideoAndAudio(videoURL: videoFile, audioURL: audioFile, outputURL: mergedURL)
                }
                return mergedURL
            }
        }

        // Fallback for muxed streams (TikTok, Instagram, Twitter, etc.)
        let muxedDir = job.jobDir.appendingPathComponent("m", isDirectory: true)
        try? FileManager.default.createDirectory(at: muxedDir, withIntermediateDirectories: true)
        let mOut = try runYtDlp(
            job: job,
            args: [
                "--newline", "--no-playlist", "--playlist-items", "1", "--no-mtime",
                "-f", selectors.muxedFallback,
                "-o", muxedDir.appendingPathComponent("%(title).90B.%(ext)s").path,
                job.req.url,
            ],
            stageLabel: "Descargando video..."
        )
        guard mOut.code == 0, let file = largestMediaFile(in: muxedDir) else {
            throw MediaValidationError.message(mOut.errorMessage ?? "No se pudo descargar el video.")
        }
        return file
    }

    private func executeAudioJob(_ job: JobRecord) throws -> URL {
        let audioDir = job.jobDir.appendingPathComponent("audio", isDirectory: true)
        try? FileManager.default.createDirectory(at: audioDir, withIntermediateDirectories: true)

        let out = try runYtDlp(
            job: job,
            args: [
                "--newline", "--no-playlist", "--playlist-items", "1", "--no-mtime",
                "-f", "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio/best",
                "-o", audioDir.appendingPathComponent("%(title).90B.%(ext)s").path,
                job.req.url,
            ],
            stageLabel: "Descargando audio..."
        )
        guard out.code == 0, let rawFile = largestMediaFile(in: audioDir) else {
            throw MediaValidationError.message(out.errorMessage ?? "No se pudo descargar el audio.")
        }

        if job.req.audioFormat == "m4a" && rawFile.pathExtension.lowercased() != "m4a" {
            updateJob(job) {
                $0.status = "processing"
                $0.stage = "Convirtiendo audio a M4A..."
                $0.percent = 99.0
                $0.speed = nil
                $0.eta = 0
            }
            let baseName = rawFile.deletingPathExtension().lastPathComponent
            let m4aURL = job.jobDir.appendingPathComponent("\(baseName).m4a")
            try runAsyncBlocking {
                try await AVMediaMuxer.exportM4AAudio(sourceURL: rawFile, outputURL: m4aURL)
            }
            return m4aURL
        }
        return rawFile
    }

    private func runYtDlp(job: JobRecord, args: [String], stageLabel: String) throws -> YTDLP.Output {
        var lastEmit = Date(timeIntervalSince1970: 0)
        let out = try YTDLP.shared.run(args, id: job.jobId) { [weak self] line, _ in
            guard let self else { return }
            let now = Date()
            if line.contains("[download]") && line.contains("%") {
                let parsed = self.parseProgressLine(line)
                if now.timeIntervalSince(lastEmit) >= 0.15 {
                    lastEmit = now
                    self.updateJob(job) {
                        $0.status = "downloading"
                        $0.stage = stageLabel
                        if let p = parsed.percent { $0.percent = min(99.0, p) }
                        if let s = parsed.speed { $0.speed = s }
                        if let e = parsed.eta { $0.eta = e }
                        if let t = parsed.total {
                            $0.totalBytes = t
                            $0.downloadedBytes = Int64(Double(t) * ($0.percent / 100.0))
                        }
                    }
                }
            }
        }
        lock.lock()
        let isCancelled = job.cancelled
        lock.unlock()
        if isCancelled || out.code == 130 {
            throw CancellationError()
        }
        return out
    }

    private func parseProgressLine(_ line: String) -> (percent: Double?, speed: Double?, eta: Int?, total: Int64?) {
        var percent: Double?
        var speed: Double?
        var eta: Int?
        var total: Int64?

        if let pRange = line.range(of: #"(\d+(?:\.\d+)?)%"#, options: .regularExpression) {
            let numStr = line[pRange].dropLast()
            percent = Double(numStr)
        }
        if let sRange = line.range(of: #"of\s+~?\s*([\d.]+)\s*(GiB|MiB|KiB|GB|MB|KB|B)"#, options: [.regularExpression, .caseInsensitive]) {
            let sub = String(line[sRange])
            total = parseSizeToken(sub)
        }
        if let vRange = line.range(of: #"at\s+([\d.]+)\s*(GiB|MiB|KiB|GB|MB|KB|B)/s"#, options: [.regularExpression, .caseInsensitive]) {
            let sub = String(line[vRange])
            speed = parseSizeToken(sub).map { Double($0) }
        }
        if let eRange = line.range(of: #"ETA\s+(\d+):(\d+)"#, options: .regularExpression) {
            let sub = String(line[eRange]).replacingOccurrences(of: "ETA", with: "").trimmingCharacters(in: .whitespaces)
            let parts = sub.split(separator: ":").compactMap { Int($0) }
            if parts.count == 2 {
                eta = parts[0] * 60 + parts[1]
            }
        }
        return (percent, speed, eta, total)
    }

    private func parseSizeToken(_ text: String) -> Int64? {
        guard let numRange = text.range(of: #"[\d.]+"#, options: .regularExpression),
              let num = Double(text[numRange]),
              let unitRange = text.range(of: #"(GiB|MiB|KiB|GB|MB|KB|B)"#, options: [.regularExpression, .caseInsensitive]) else {
            return nil
        }
        let unit = text[unitRange].lowercased()
        let mult: Double
        switch unit {
        case "gib", "gb": mult = 1024.0 * 1024.0 * 1024.0
        case "mib", "mb": mult = 1024.0 * 1024.0
        case "kib", "kb": mult = 1024.0
        default: mult = 1.0
        }
        return Int64(num * mult)
    }

    private func largestMediaFile(in dir: URL) -> URL? {
        let ignored = Set(["part", "ytdl", "temp", "tmp", "webp", "jpg", "jpeg", "png", "json"])
        let files = (try? FileManager.default.contentsOfDirectory(
            at: dir,
            includingPropertiesForKeys: [.fileSizeKey, .isRegularFileKey]
        )) ?? []
        return files.filter { url in
            let ext = url.pathExtension.lowercased()
            return !ignored.contains(ext)
        }.max { a, b in
            let sa = (try? a.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            let sb = (try? b.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
            return sa < sb
        }
    }

    private func moveUniqueToDocuments(_ src: URL, preferredName: String) throws -> URL {
        let fm = FileManager.default
        let destDir = Self.documentsDownloadDir()
        var target = destDir.appendingPathComponent(preferredName)
        if fm.fileExists(atPath: target.path) {
            let stem = (preferredName as NSString).deletingPathExtension
            let ext = (preferredName as NSString).pathExtension
            var counter = 1
            while fm.fileExists(atPath: target.path) {
                let name = ext.isEmpty ? "\(stem) (\(counter))" : "\(stem) (\(counter)).\(ext)"
                target = destDir.appendingPathComponent(name)
                counter += 1
            }
        }
        try fm.moveItem(at: src, to: target)
        return target
    }

    private func runAsyncBlocking(_ block: @escaping () async throws -> Void) throws {
        let sem = DispatchSemaphore(value: 0)
        var capturedError: Error?
        Task {
            do {
                try await block()
            } catch {
                capturedError = error
            }
            sem.signal()
        }
        sem.wait()
        if let err = capturedError {
            throw err
        }
    }
}
