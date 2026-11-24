import UIKit
import WebKit

final class WebViewController: UIViewController, WKNavigationDelegate, WKScriptMessageHandler {
    private let serverPort: UInt16
    private var webView: WKWebView!
    private var isDarkTheme: Bool = true

    init(serverPort: UInt16) {
        self.serverPort = serverPort
        super.init(nibName: nil, bundle: nil)
        let saved = UserDefaults.standard.string(forKey: "exclaim_theme") ?? "dark"
        self.isDarkTheme = saved != "light"
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override var preferredStatusBarStyle: UIStatusBarStyle {
        isDarkTheme ? .lightContent : .darkContent
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = isDarkTheme ? UIColor(red: 0.027, green: 0.035, blue: 0.055, alpha: 1) : UIColor(red: 0.929, green: 0.941, blue: 0.965, alpha: 1)

        let userContent = WKUserContentController()
        userContent.add(self, name: "iosBridge")

        let config = WKWebViewConfiguration()
        config.userContentController = userContent
        config.allowsInlineMediaPlayback = true

        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.translatesAutoresizingMaskIntoConstraints = false

        view.addSubview(webView)
        NSLayoutConstraint.activate([
            webView.topAnchor.constraint(equalTo: view.topAnchor),
            webView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
        ])

        if let url = URL(string: "http://127.0.0.1:\(serverPort)/") {
            webView.load(URLRequest(url: url))
        }
    }

    func presentShareSheet(for url: URL) {
        let activity = UIActivityViewController(activityItems: [url], applicationActivities: nil)
        if let pop = activity.popoverPresentationController {
            pop.sourceView = view
            pop.sourceRect = CGRect(x: view.bounds.midX, y: view.bounds.maxY - 60, width: 1, height: 1)
        }
        present(activity, animated: true)
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let action = body["action"] as? String else {
            return
        }
        if action == "setTheme", let theme = body["theme"] as? String {
            isDarkTheme = theme != "light"
            view.backgroundColor = isDarkTheme ? UIColor(red: 0.027, green: 0.035, blue: 0.055, alpha: 1) : UIColor(red: 0.929, green: 0.941, blue: 0.965, alpha: 1)
            setNeedsStatusBarAppearanceUpdate()
        } else if action == "openExternalUrl", let raw = body["url"] as? String, let url = URL(string: raw),
                  url.scheme?.lowercased() == "http" || url.scheme?.lowercased() == "https" {
            UIApplication.shared.open(url)
        }
    }

    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        guard let url = navigationAction.request.url else {
            decisionHandler(.allow)
            return
        }
        let host = url.host?.lowercased()
        if host == "127.0.0.1" || host == "localhost" {
            decisionHandler(.allow)
        } else if url.scheme?.lowercased() == "http" || url.scheme?.lowercased() == "https" {
            UIApplication.shared.open(url)
            decisionHandler(.cancel)
        } else {
            decisionHandler(.allow)
        }
    }
}
