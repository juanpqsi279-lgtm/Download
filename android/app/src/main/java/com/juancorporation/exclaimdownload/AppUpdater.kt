package com.juancorporation.exclaimdownload

import android.content.Context
import android.content.Intent
import android.os.Build
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

    fun downloadAndInstallApk(context: Context, assetUrl: String, assetName: String): JSONObject {
        val uri = URI(assetUrl.trim())
        val host = uri.host?.lowercase(Locale.ROOT).orEmpty()
        if (uri.scheme?.lowercase(Locale.ROOT) != "https" || host !in ALLOWED_GITHUB_HOSTS) {
            throw IllegalArgumentException("La URL de actualización debe provenir de GitHub Releases.")
        }

        val safeName = File(assetName).name.ifBlank { "Download-update.apk" }
        if (!safeName.lowercase(Locale.ROOT).endsWith(".apk")) {
            throw IllegalArgumentException("El paquete de actualización debe ser un archivo .apk.")
        }

        val updatesDir = File(context.cacheDir, "updates").apply { mkdirs() }
        val apkFile = File(updatesDir, safeName)

        val conn = (URL(assetUrl).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = true
            connectTimeout = 20_000
            readTimeout = 60_000
            setRequestProperty("User-Agent", "!Download-Android/${BuildConfig.VERSION_NAME}")
        }
        val code = conn.responseCode
        if (code !in 200..299) {
            throw IllegalStateException("Error al descargar el APK (HTTP $code).")
        }

        conn.inputStream.use { input ->
            apkFile.outputStream().use { out ->
                input.copyTo(out)
            }
        }

        val contentUri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            apkFile,
        )
        val installIntent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(contentUri, "application/vnd.android.package-archive")
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
        }
        context.startActivity(installIntent)

        return JSONObject().apply {
            put("started", true)
            put("message", "APK descargado. Acepta la instalación en Android para actualizar !Download.")
        }
    }
}
