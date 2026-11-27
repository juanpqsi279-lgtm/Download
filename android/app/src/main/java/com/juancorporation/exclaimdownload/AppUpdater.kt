package com.juancorporation.exclaimdownload

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.core.content.FileProvider
import com.yausername.youtubedl_android.YoutubeDL
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URI
import java.net.URL
import java.util.Locale

object AppUpdater {
    const val GITHUB_REPO = "juanpqsi279-lgtm/Download"

    @Volatile
    private var pendingApkFile: File? = null

    private val ALLOWED_GITHUB_HOSTS = setOf(
        "github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
    )

    suspend fun updateEngine(app: DownloadApp): JSONObject {
        val status = app.ensureEngineReady()
        if (!status.ready) {
            return JSONObject().apply {
                put("updated", false)
                put("current_version", JSONObject.NULL)
                put("latest_version", JSONObject.NULL)
                put("restart_required", false)
                put("message", status.error ?: "El motor yt-dlp aún no está listo.")
            }
        }

        val beforeVersion = runCatching { YoutubeDL.getInstance().version(app) }.getOrNull()
        return try {
            val updateResult = YoutubeDL.getInstance().updateYoutubeDL(app, YoutubeDL.UpdateChannel.STABLE)
            val afterVersion = runCatching { YoutubeDL.getInstance().version(app) }.getOrNull() ?: beforeVersion
            val updated = updateResult == YoutubeDL.UpdateStatus.DONE
            JSONObject().apply {
                put("updated", updated)
                put("current_version", afterVersion ?: "Disponible")
                put("latest_version", afterVersion ?: JSONObject.NULL)
                put("restart_required", false)
                put(
                    "message",
                    if (updated) {
                        "Motor actualizado a yt-dlp ${afterVersion ?: "más reciente"}."
                    } else {
                        "El motor yt-dlp ya está al día (${afterVersion ?: "última versión"})."
                    }
                )
            }
        } catch (exc: Exception) {
            JSONObject().apply {
                put("updated", false)
                put("current_version", beforeVersion ?: JSONObject.NULL)
                put("latest_version", JSONObject.NULL)
                put("restart_required", false)
                put("message", "No se pudo actualizar el motor: ${exc.message ?: "error de red"}")
            }
        }
    }

    fun checkAppUpdate(): JSONObject {
        val currentVersion = BuildConfig.VERSION_NAME
        val apiUrl = "https://api.github.com/repos/$GITHUB_REPO/releases/latest"
        val releasesUrl = "https://github.com/$GITHUB_REPO/releases"

        return try {
            val conn = (URL(apiUrl).openConnection() as HttpURLConnection).apply {
                connectTimeout = 15_000
                readTimeout = 15_000
                setRequestProperty("Accept", "application/vnd.github+json")
                setRequestProperty("User-Agent", "!Download-Android/$currentVersion")
            }
            val code = conn.responseCode
            if (code == 404) {
                return JSONObject().apply {
                    put("update_available", false)
                    put("current_version", currentVersion)
                    put("latest_version", JSONObject.NULL)
                    put("release_notes", JSONObject.NULL)
                    put("release_url", releasesUrl)
                    put("asset_name", JSONObject.NULL)
                    put("asset_url", JSONObject.NULL)
                    put("asset_size", JSONObject.NULL)
                    put("message", "Aún no hay lanzamientos publicados en GitHub.")
                }
            }
            if (code !in 200..299) {
                throw IllegalStateException("HTTP $code")
            }

            val body = conn.inputStream.bufferedReader().use { it.readText() }
            val release = JSONObject(body)
            val latestTag = release.optString("tag_name", "").removePrefix("v")
            val isNewer = MediaParser.compareSemver(
                MediaParser.parseSemver(latestTag),
                MediaParser.parseSemver(currentVersion),
            ) > 0

            val assets = release.optJSONArray("assets") ?: JSONArray()
            val apkAsset = MediaParser.pickAndroidApkAsset(assets, Build.SUPPORTED_ABIS)

            JSONObject().apply {
                put("update_available", isNewer)
                put("current_version", currentVersion)
                put("latest_version", latestTag.ifBlank { JSONObject.NULL })
                put("release_notes", release.optString("body", "").ifBlank { JSONObject.NULL })
                put("release_url", release.optString("html_url", releasesUrl))
                put("asset_name", apkAsset?.optString("name") ?: JSONObject.NULL)
                put("asset_url", apkAsset?.optString("browser_download_url") ?: JSONObject.NULL)
                put(
                    "asset_size",
                    if (apkAsset != null && apkAsset.has("size")) apkAsset.optLong("size") else JSONObject.NULL,
                )
                put(
                    "message",
                    if (isNewer) {
                        "¡Nueva versión v$latestTag disponible!"
                    } else {
                        "Tienes la versión más reciente (v$currentVersion)."
                    }
                )
            }
        } catch (exc: Exception) {
            JSONObject().apply {
                put("update_available", false)
                put("current_version", currentVersion)
                put("latest_version", JSONObject.NULL)
                put("release_notes", JSONObject.NULL)
                put("release_url", releasesUrl)
                put("asset_name", JSONObject.NULL)
                put("asset_url", JSONObject.NULL)
                put("asset_size", JSONObject.NULL)
                put("message", "No se pudo consultar GitHub Releases: ${exc.message ?: "error de red"}")
            }
        }
    }

    private fun validateAllowedGitHubUrl(rawUrl: String): URL {
        val uri = URI(rawUrl.trim())
        val host = uri.host?.lowercase(Locale.ROOT).orEmpty()
        if (uri.scheme?.lowercase(Locale.ROOT) != "https" || host !in ALLOWED_GITHUB_HOSTS) {
            throw IllegalArgumentException("La URL de actualización debe provenir de GitHub Releases.")
        }
        return uri.toURL()
    }

    private fun openGitHubDownloadConnection(initialUrl: String): HttpURLConnection {
        var current = validateAllowedGitHubUrl(initialUrl)
        repeat(5) {
            val conn = (current.openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                connectTimeout = 25_000
                readTimeout = 180_000
                setRequestProperty("User-Agent", "!Download-Android/${BuildConfig.VERSION_NAME}")
            }
            val code = conn.responseCode
            if (code in setOf(301, 302, 303, 307, 308)) {
                val loc = conn.getHeaderField("Location")
                conn.disconnect()
                if (loc.isNullOrBlank()) {
                    throw IllegalStateException("Redirección de descarga vacía desde GitHub.")
                }
                val resolved = current.toURI().resolve(loc.trim()).toString()
                current = validateAllowedGitHubUrl(resolved)
                return@repeat
            }
            if (code !in 200..299) {
                conn.disconnect()
                throw IllegalStateException("Error al descargar el APK (HTTP $code).")
            }
            return conn
        }
        throw IllegalStateException("Demasiadas redirecciones al descargar el APK.")
    }

    @Suppress("DEPRECATION")
    private fun verifyDownloadedApk(context: Context, apkFile: File, expectedLength: Long) {
        val actualLength = apkFile.length()
        if (actualLength < 1_000_000L || (expectedLength > 0L && actualLength != expectedLength)) {
            apkFile.delete()
            throw IllegalStateException("La descarga del APK quedó incompleta. Inténtalo de nuevo.")
        }
        val magic = ByteArray(4)
        val readMagic = apkFile.inputStream().use { it.read(magic) }
        val isZip = readMagic == 4 &&
            magic[0] == 'P'.code.toByte() &&
            magic[1] == 'K'.code.toByte() &&
            magic[2] == 0x03.toByte() &&
            magic[3] == 0x04.toByte()
        if (!isZip) {
            apkFile.delete()
            throw IllegalStateException("El archivo descargado no es un paquete APK válido.")
        }
        val pkgInfo = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            context.packageManager.getPackageArchiveInfo(
                apkFile.absolutePath,
                PackageManager.PackageInfoFlags.of(0L),
            )
        } else {
            context.packageManager.getPackageArchiveInfo(apkFile.absolutePath, 0)
        }
        if (pkgInfo == null || pkgInfo.packageName != context.packageName) {
            apkFile.delete()
            throw IllegalStateException("El paquete APK descargado no corresponde a !Download.")
        }
    }

    private fun launchPackageInstaller(context: Context, apkFile: File) {
        val hostContext = MainActivity.currentActivity?.get() ?: context
        val contentUri = FileProvider.getUriForFile(
            hostContext,
            "${context.packageName}.fileprovider",
            apkFile,
        )
        val installIntent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(contentUri, "application/vnd.android.package-archive")
            flags = Intent.FLAG_GRANT_READ_URI_PERMISSION or
                Intent.FLAG_ACTIVITY_SINGLE_TOP
            if (hostContext !is android.app.Activity) {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
        }
        Handler(Looper.getMainLooper()).post {
            hostContext.startActivity(installIntent)
        }
    }

    fun installPendingApkIfPermitted(activity: MainActivity) {
        val pending = pendingApkFile ?: return
        if (!pending.isFile) {
            pendingApkFile = null
            return
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || activity.packageManager.canRequestPackageInstalls()) {
            pendingApkFile = null
            launchPackageInstaller(activity, pending)
        }
    }

    fun downloadAndInstallApk(context: Context, assetUrl: String, assetName: String): JSONObject {
        validateAllowedGitHubUrl(assetUrl)

        val safeName = File(assetName).name.ifBlank { "Download-update.apk" }
        if (!safeName.lowercase(Locale.ROOT).endsWith(".apk")) {
            throw IllegalArgumentException("El paquete de actualización debe ser un archivo .apk.")
        }

        val updatesDir = File(context.cacheDir, "updates").apply { mkdirs() }
        updatesDir.listFiles()?.forEach { oldFile ->
            if (oldFile.isFile) {
                oldFile.delete()
            }
        }

        val tmpFile = File(updatesDir, "$safeName.tmp")
        val apkFile = File(updatesDir, safeName)
        var expectedLength = -1L

        val conn = openGitHubDownloadConnection(assetUrl)
        try {
            expectedLength = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                conn.contentLengthLong
            } else {
                conn.contentLength.toLong()
            }
            conn.inputStream.use { input ->
                tmpFile.outputStream().use { out ->
                    input.copyTo(out)
                }
            }
        } finally {
            conn.disconnect()
        }

        verifyDownloadedApk(context, tmpFile, expectedLength)
        apkFile.delete()
        if (!tmpFile.renameTo(apkFile)) {
            tmpFile.copyTo(apkFile, overwrite = true)
            tmpFile.delete()
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !context.packageManager.canRequestPackageInstalls()) {
            pendingApkFile = apkFile
            val hostContext = MainActivity.currentActivity?.get() ?: context
            val permIntent = Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${context.packageName}"),
            ).apply {
                if (hostContext !is android.app.Activity) {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
            }
            Handler(Looper.getMainLooper()).post {
                hostContext.startActivity(permIntent)
            }
            return JSONObject().apply {
                put("started", true)
                put("permission_required", true)
                put(
                    "message",
                    "APK descargado y verificado. Activa 'Permitir desde esta fuente' y vuelve a !Download para instalarlo automáticamente.",
                )
            }
        }

        pendingApkFile = null
        launchPackageInstaller(context, apkFile)

        return JSONObject().apply {
            put("started", true)
            put("permission_required", false)
            put("message", "APK descargado y verificado. Acepta la instalación en Android para actualizar !Download.")
        }
    }
}
