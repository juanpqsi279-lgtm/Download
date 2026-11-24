package com.juancorporation.exclaimdownload

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

data class EngineInitStatus(val ready: Boolean, val error: String? = null)

class DownloadApp : Application() {

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val engineDeferred = CompletableDeferred<EngineInitStatus>()

    lateinit var downloadEngine: DownloadManagerEngine
        private set

    lateinit var localServer: LocalApiServer
        private set

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannels()

        downloadEngine = DownloadManagerEngine(this)
        localServer = LocalApiServer(this, downloadEngine).also { it.start() }

        appScope.launch {
            try {
                YoutubeDL.getInstance().init(this@DownloadApp)
                FFmpeg.getInstance().init(this@DownloadApp)
                engineDeferred.complete(EngineInitStatus(ready = true))
            } catch (exc: Exception) {
                engineDeferred.complete(
                    EngineInitStatus(
                        ready = false,
                        error = "No se pudo inicializar el motor multimedia: ${exc.message ?: "error desconocido"}",
                    )
                )
            }
        }
    }

    suspend fun ensureEngineReady(): EngineInitStatus = engineDeferred.await()

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val progressChannel = NotificationChannel(
            DownloadForegroundService.CHANNEL_PROGRESS,
            "Descargas en curso",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Muestra el progreso de descargas activas de !Download"
        }

        val completeChannel = NotificationChannel(
            DownloadForegroundService.CHANNEL_COMPLETE,
            "Descargas completadas",
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = "Notifica cuando un video o audio termina de guardarse"
        }

        nm.createNotificationChannel(progressChannel)
        nm.createNotificationChannel(completeChannel)
    }

    companion object {
        lateinit var instance: DownloadApp
            private set
    }
}
