import Foundation
import YTDLP

final class AppUpdater {
    static let githubRepo = "juanpqsi279-lgtm/Download"

    static func appVersion() -> String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.4.0"
    }

    static func runtimeToolsJson() -> [String: Any] {
        let versions = (try? YTDLP.shared.versions()) ?? [:]
        let ytVer = versions["yt_dlp"] ?? "Listo"
        let pyVer = versions["python"] ?? "3.14"

        return [
            "yt_dlp": [
                "available": true,
                "version": ytVer,
                "using_override": false,
            ],
            "ffmpeg": [
                "available": true,
                "version": "AVFoundation (Nativo iOS)",
            ],
            "ffprobe": [
                "available": true,
                "version": "Python \(pyVer)",
            ],
            "deno": [
                "available": true,
                "version": "Apple JavaScriptCore",
            ],
        ]
    }

    static func checkAppUpdate() -> [String: Any] {
        let current = appVersion()
        let apiUrl = URL(string: "https://api.github.com/repos/\(githubRepo)/releases/latest")!
        let releasesPage = "https://github.com/\(githubRepo)/releases"

        var request = URLRequest(url: apiUrl, timeoutInterval: 15)
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("!Download-iOS/\(current)", forHTTPHeaderField: "User-Agent")

        let sem = DispatchSemaphore(value: 0)
        var result: [String: Any] = [
            "update_available": false,
            "current_version": current,
            "latest_version": NSNull(),
            "release_notes": NSNull(),
            "release_url": releasesPage,
            "asset_name": NSNull(),
            "asset_url": NSNull(),
            "asset_size": NSNull(),
            "message": "No se pudo consultar GitHub Releases.",
        ]

        URLSession.shared.dataTask(with: request) { data, response, error in
            defer { sem.signal() }
            if let error {
                result["message"] = "No se pudo conectar con GitHub Releases: \(error.localizedDescription)"
                return
            }
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            if code == 404 {
                result["message"] = "Aún no hay lanzamientos publicados en GitHub."
                return
            }
            guard (200...299).contains(code), let data,
                  let release = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
                result["message"] = "Respuesta inválida de GitHub (HTTP \(code))."
                return
            }

            let rawTag = (release["tag_name"] as? String) ?? ""
            let latestTag = rawTag.hasPrefix("v") ? String(rawTag.dropFirst()) : rawTag
            let isNewer = MediaParser.compareSemver(
                MediaParser.parseSemver(latestTag),
                MediaParser.parseSemver(current)
            ) > 0

            let assets = release["assets"] as? [[String: Any]] ?? []
            let ipaAsset = MediaParser.pickIOSIpaAsset(assets)

            result = [
                "update_available": isNewer,
                "current_version": current,
                "latest_version": latestTag.isEmpty ? NSNull() : latestTag,
                "release_notes": (release["body"] as? String)?.isEmpty == false ? release["body"]! : NSNull(),
                "release_url": (release["html_url"] as? String) ?? releasesPage,
                "asset_name": (ipaAsset?["name"] as? String) ?? NSNull(),
                "asset_url": (ipaAsset?["browser_download_url"] as? String) ?? NSNull(),
                "asset_size": ipaAsset?["size"] ?? NSNull(),
                "message": isNewer
                    ? "¡Nueva versión v\(latestTag) disponible en Releases (AltStore / SideStore)!"
                    : "Tienes la versión más reciente (v\(current)).",
            ]
        }.resume()

        sem.wait()
        return result
    }
}
