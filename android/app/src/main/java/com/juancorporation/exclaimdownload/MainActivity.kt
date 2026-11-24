package com.juancorporation.exclaimdownload

import android.Manifest
import android.annotation.SuppressLint
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsControllerCompat
import org.json.JSONObject

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private var pageLoaded = false
    private var pendingSharedUrl: String? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        WindowCompat.setDecorFitsSystemWindows(window, false)
        applySystemBarTheme(
            getSharedPreferences("exclaim_download_prefs", Context.MODE_PRIVATE)
                .getString("theme", "dark") ?: "dark",
        )

        webView = WebView(this).apply {
            setBackgroundColor(Color.parseColor("#07090e"))
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                allowFileAccess = false
                allowContentAccess = false
                mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            }
            addJavascriptInterface(AndroidBridge(), "AndroidBridge")
            webChromeClient = WebChromeClient()
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val uri = request.url ?: return false
                    if (uri.host == "127.0.0.1" || uri.host == "localhost") {
                        return false
                    }
                    openExternal(uri.toString())
                    return true
                }

                override fun onPageFinished(view: WebView, url: String?) {
                    super.onPageFinished(view, url)
                    pageLoaded = true
                    flushPendingSharedUrl()
                }
            }
        }
        setContentView(webView)

        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (webView.canGoBack()) {
                        webView.goBack()
                    } else {
                        isEnabled = false
                        onBackPressedDispatcher.onBackPressed()
                    }
                }
            },
        )

        extractShareIntentUrl(intent)
        val serverPort = DownloadApp.instance.localServer.port
        webView.loadUrl("http://127.0.0.1:$serverPort/")
        requestNotificationPermissionIfNeeded()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        extractShareIntentUrl(intent)
        if (pageLoaded) {
            flushPendingSharedUrl()
        }
    }

    private fun extractShareIntentUrl(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND) return
        val shared = intent.getStringExtra(Intent.EXTRA_TEXT)
        val extracted = MediaParser.extractFirstUrl(shared)
        if (!extracted.isNullOrBlank()) {
            pendingSharedUrl = extracted
        }
    }

    private fun flushPendingSharedUrl() {
        val url = pendingSharedUrl ?: return
        pendingSharedUrl = null
        val quoted = JSONObject.quote(url)
        webView.post {
            webView.evaluateJavascript("if (window.__receiveSharedUrl) { window.__receiveSharedUrl($quoted); }", null)
        }
    }

    private fun applySystemBarTheme(theme: String) {
        val isLight = theme == "light"
        runOnUiThread {
            window.statusBarColor = Color.TRANSPARENT
            window.navigationBarColor = Color.TRANSPARENT
            val controller = WindowInsetsControllerCompat(window, window.decorView)
            controller.isAppearanceLightStatusBars = isLight
            controller.isAppearanceLightNavigationBars = isLight
        }
    }

    private fun openExternal(url: String) {
        if (!url.startsWith("http://") && !url.startsWith("https://")) return
        runCatching {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        if (
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1001)
        }
    }

    inner class AndroidBridge {
        @JavascriptInterface
        fun setSystemBarTheme(theme: String) {
            applySystemBarTheme(theme)
        }

        @JavascriptInterface
        fun openExternalUrl(url: String) {
            openExternal(url)
        }

        @JavascriptInterface
        fun readClipboardText(): String {
            var text = ""
            runOnUiThreadSync {
                val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                val clip = cm.primaryClip
                if (clip != null && clip.itemCount > 0) {
                    text = clip.getItemAt(0).coerceToText(this@MainActivity)?.toString().orEmpty()
                }
            }
            return text
        }
    }

    private fun runOnUiThreadSync(block: () -> Unit) {
        val latch = java.util.concurrent.CountDownLatch(1)
        runOnUiThread {
            try {
                block()
            } finally {
                latch.countDown()
            }
        }
        latch.await()
    }
}
