package com.juancorporation.exclaimdownload

import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

class DownloadForegroundService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                    stopForeground(STOP_FOREGROUND_REMOVE)
                } else {
                    @Suppress("DEPRECATION")
                    stopForeground(true)
                }
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                val title = intent?.getStringExtra(EXTRA_TITLE) ?: "!Download"
                val stage = intent?.getStringExtra(EXTRA_STAGE) ?: "Descargando..."
                val percent = intent?.getIntExtra(EXTRA_PERCENT, 0) ?: 0
                val indeterminate = intent?.getBooleanExtra(EXTRA_INDETERMINATE, true) ?: true

                val notification = buildProgressNotification(title, stage, percent, indeterminate)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    startForeground(
                        PROGRESS_NOTIFICATION_ID,
                        notification,
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
                    )
                } else {
                    startForeground(PROGRESS_NOTIFICATION_ID, notification)
                }
                return START_NOT_STICKY
            }
        }
    }

    private fun buildProgressNotification(
        title: String,
        stage: String,
        percent: Int,
        indeterminate: Boolean,
    ) = NotificationCompat.Builder(this, CHANNEL_PROGRESS)
        .setSmallIcon(android.R.drawable.stat_sys_download)
        .setContentTitle(title)
        .setContentText(stage)
        .setOnlyAlertOnce(true)
        .setOngoing(true)
        .setProgress(100, percent.coerceIn(0, 100), indeterminate)
        .setContentIntent(
            PendingIntent.getActivity(
                this,
                0,
                Intent(this, MainActivity::class.java).apply {
                    flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
                },
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        )
        .build()

    companion object {
        const val CHANNEL_PROGRESS = "downloads_progress"
        const val CHANNEL_COMPLETE = "downloads_complete"
        private const val PROGRESS_NOTIFICATION_ID = 2001

        private const val ACTION_UPDATE = "com.juancorporation.exclaimdownload.action.PROGRESS"
        private const val ACTION_STOP = "com.juancorporation.exclaimdownload.action.STOP"

        private const val EXTRA_TITLE = "extra_title"
        private const val EXTRA_STAGE = "extra_stage"
        private const val EXTRA_PERCENT = "extra_percent"
        private const val EXTRA_INDETERMINATE = "extra_indeterminate"

        fun updateProgress(
            context: Context,
            title: String,
            stage: String,
            percent: Int,
            indeterminate: Boolean,
        ) {
            val intent = Intent(context, DownloadForegroundService::class.java).apply {
                action = ACTION_UPDATE
                putExtra(EXTRA_TITLE, title)
                putExtra(EXTRA_STAGE, stage)
                putExtra(EXTRA_PERCENT, percent)
                putExtra(EXTRA_INDETERMINATE, indeterminate)
            }
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
            } catch (_: Exception) {
                // Background restrictions may prevent starting service in edge cases
            }
        }

        fun stop(context: Context) {
            try {
                context.stopService(Intent(context, DownloadForegroundService::class.java))
            } catch (_: Exception) {
                // Ignore
            }
        }

        fun postCompletedNotification(
            context: Context,
            title: String,
            qualityLabel: String,
            contentUri: Uri,
            mimeType: String,
        ) {
            val viewIntent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(contentUri, mimeType)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
            }
            val pendingIntent = PendingIntent.getActivity(
                context,
                title.hashCode(),
                viewIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )

            val notification = NotificationCompat.Builder(context, CHANNEL_COMPLETE)
                .setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle(title)
                .setContentText("Guardado en Descargas · $qualityLabel")
                .setAutoCancel(true)
                .setContentIntent(pendingIntent)
                .build()

            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.notify((System.currentTimeMillis() and 0xFFFF).toInt() + 3000, notification)
        }
    }
}
