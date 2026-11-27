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
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsControllerCompat
import org.json.JSONObject
import java.lang.ref.WeakReference

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private var pageLoaded = false
    private var pendingSharedUrl: String? = null
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null

    private val fileChooserLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        val callback = fileChooserCallback
        fileChooserCallback = null
        if (callback == null) return@registerForActivityResult
        val data = result.data
        val uris: Array<Uri>? = if (result.resultCode == RESULT_OK && data != null) {
            val clip = data.clipData
            when {
                clip != null && clip.itemCount > 0 ->
                    Array(clip.itemCount) { i -> clip.getItemAt(i).uri }
                data.data != null -> arrayOf(data.data!!)
                else -> null
            }
        } else {
            null
        }
        callback.onReceiveValue(uris)
    }

    companion object {
        @Volatile
        var currentActivity: WeakReference<MainActivity>? = null
    }

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
            webChromeClient = object : WebChromeClient() {
                override fun onShowFileChooser(
                    webView: WebView?,
                    filePathCallback: ValueCallback<Array<Uri>>?,
                    fileChooserParams: FileChooserParams?,
                ): Boolean {
                    fileChooserCallback?.onReceiveValue(null)
                    fileChooserCallback = filePathCallback
                    val accept = fileChooserParams?.acceptTypes?.filter { it.isNotBlank() }?.toTypedArray()
                    val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = if (accept != null && accept.size == 1) accept[0] else "*/*"
                        if (accept != null && accept.size > 1) {
                            putExtra(Intent.EXTRA_MIME_TYPES, accept)
                        }
                        if (fileChooserParams?.mode == FileChooserParams.MODE_OPEN_MULTIPLE) {
                            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                        }
                    }
                    return try {
                        fileChooserLauncher.launch(intent)
                        true
                    } catch (_: Exception) {
                        fileChooserCallback = null
                        false
                    }
                }
            }
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
        requestStartupPermissionsIfNeeded()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray,
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 1002 && pageLoaded) {
            webView.post {
                webView.evaluateJavascript("if (window.ExclaimPlayer && window.ExclaimPlayer.refreshLibrary) { window.ExclaimPlayer.refreshLibrary(); }", null)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        currentActivity = WeakReference(this)
        AppUpdater.installPendingApkIfPermitted(this)
    }

    override fun onDestroy() {
        if (currentActivity?.get() === this) {
            currentActivity = null
        }
        super.onDestroy()
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

    fun hasMediaReadPermission(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(this, Manifest.permission.READ_MEDIA_AUDIO) == PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.READ_MEDIA_VIDEO) == PackageManager.PERMISSION_GRANTED
        } else {
            ContextCompat.checkSelfPermission(this, Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun requiredMediaPermissions(): Array<String> {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            arrayOf(Manifest.permission.READ_MEDIA_AUDIO, Manifest.permission.READ_MEDIA_VIDEO)
        } else {
            arrayOf(Manifest.permission.READ_EXTERNAL_STORAGE)
        }
    }

    private fun requestStartupPermissionsIfNeeded() {
        val perms = mutableListOf<String>()
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            perms.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        if (!hasMediaReadPermission()) {
            perms.addAll(requiredMediaPermissions())
        }
        if (perms.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, perms.toTypedArray(), 1002)
        }
    }

    inner class AndroidBridge {
        @JavascriptInterface
        fun hasMediaPermission(): Boolean = hasMediaReadPermission()

        @JavascriptInterface
        fun requestMediaPermission() {
            runOnUiThread {
                ActivityCompat.requestPermissions(this@MainActivity, requiredMediaPermissions(), 1002)
            }
        }

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
