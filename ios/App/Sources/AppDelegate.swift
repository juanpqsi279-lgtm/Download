import UIKit
import YTDLP

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    var window: UIWindow?
    private let downloadEngine = DownloadManagerEngine()
    private var localServer: LocalHTTPServer?
    private weak var rootController: WebViewController?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        DispatchQueue.global(qos: .userInitiated).async {
            try? YTDLP.shared.start()
        }

        let server = LocalHTTPServer(engine: downloadEngine) { [weak self] targetURL in
            self?.rootController?.presentShareSheet(for: targetURL)
        }
        let port = (try? server.start()) ?? 0
        self.localServer = server

        let controller = WebViewController(serverPort: port)
        self.rootController = controller

        let win = UIWindow(frame: UIScreen.main.bounds)
        win.rootViewController = controller
        win.makeKeyAndVisible()
        self.window = win
        return true
    }

    func applicationWillTerminate(_ application: UIApplication) {
        localServer?.stop()
    }
}
