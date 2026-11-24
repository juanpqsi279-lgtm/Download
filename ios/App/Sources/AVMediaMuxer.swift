import AVFoundation
import Foundation

enum AVMediaMuxer {
    enum MuxError: LocalizedError {
        case missingTracks
        case exportFailed(String)

        var errorDescription: String? {
            switch self {
            case .missingTracks:
                return "No se encontraron pistas válidas de video o audio para unir."
            case .exportFailed(let reason):
                return "No se pudo ensamblar el archivo MP4: \(reason)"
            }
        }
    }

    static func muxVideoAndAudio(videoURL: URL, audioURL: URL, outputURL: URL) async throws {
        let composition = AVMutableComposition()
        let videoAsset = AVURLAsset(url: videoURL)
        let audioAsset = AVURLAsset(url: audioURL)

        let videoTracks = try await videoAsset.loadTracks(withMediaType: .video)
        let audioTracks = try await audioAsset.loadTracks(withMediaType: .audio)
        guard let srcVideo = videoTracks.first, let srcAudio = audioTracks.first else {
            throw MuxError.missingTracks
        }

        let videoDuration = try await videoAsset.load(.duration)
        let audioDuration = try await audioAsset.load(.duration)

        guard let dstVideo = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid),
              let dstAudio = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) else {
            throw MuxError.missingTracks
        }

        try dstVideo.insertTimeRange(CMTimeRange(start: .zero, duration: videoDuration), of: srcVideo, at: .zero)
        let audioRange = CMTimeRange(start: .zero, duration: CMTimeMinimum(videoDuration, audioDuration))
        try dstAudio.insertTimeRange(audioRange, of: srcAudio, at: .zero)

        let fm = FileManager.default
        if fm.fileExists(atPath: outputURL.path) {
            try fm.removeItem(at: outputURL)
        }

        guard let session = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetPassthrough) else {
            throw MuxError.exportFailed("Sesión de exportación no disponible.")
        }
        session.outputURL = outputURL
        session.outputFileType = .mp4
        session.shouldOptimizeForNetworkUse = true

        await withCheckedContinuation { continuation in
            session.exportAsynchronously {
                continuation.resume()
            }
        }

        if session.status != .completed {
            throw MuxError.exportFailed(session.error?.localizedDescription ?? "estado \(session.status.rawValue)")
        }
    }

    static func exportM4AAudio(sourceURL: URL, outputURL: URL) async throws {
        let asset = AVURLAsset(url: sourceURL)
        let fm = FileManager.default
        if fm.fileExists(atPath: outputURL.path) {
            try fm.removeItem(at: outputURL)
        }

        guard let session = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetAppleM4A) else {
            throw MuxError.exportFailed("Conversión M4A no disponible.")
        }
        session.outputURL = outputURL
        session.outputFileType = .m4a

        await withCheckedContinuation { continuation in
            session.exportAsynchronously {
                continuation.resume()
            }
        }

        if session.status != .completed {
            throw MuxError.exportFailed(session.error?.localizedDescription ?? "estado \(session.status.rawValue)")
        }
    }
}
