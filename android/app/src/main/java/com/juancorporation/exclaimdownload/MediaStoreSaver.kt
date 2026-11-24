package com.juancorporation.exclaimdownload

import android.content.ContentValues
import android.content.Context
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.FileProvider
import java.io.File
import java.io.IOException
import java.util.Locale

data class SavedMedia(
    val displayPath: String,
    val contentUri: Uri,
    val mimeType: String,
    val fileName: String,
    val sizeBytes: Long,
)

object MediaStoreSaver {
    private val MIME_TYPES = mapOf(
        "mp4" to "video/mp4",
        "mkv" to "video/x-matroska",
        "webm" to "video/webm",
        "mp3" to "audio/mpeg",
        "m4a" to "audio/mp4",
        "opus" to "audio/opus",
        "ogg" to "audio/ogg",
        "flac" to "audio/flac",
        "wav" to "audio/wav",
    )

    fun mimeTypeForFile(file: File): String {
        val ext = file.extension.lowercase(Locale.ROOT)
        return MIME_TYPES[ext] ?: "application/octet-stream"
    }

    fun saveToDownloads(context: Context, sourceFile: File): SavedMedia {
        if (!sourceFile.isFile) {
            throw IOException("El archivo descargado no existe.")
        }

        val mimeType = mimeTypeForFile(sourceFile)
        val sizeBytes = sourceFile.length()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val resolver = context.contentResolver
            val relPath = "${Environment.DIRECTORY_DOWNLOADS}/!Download"
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, sourceFile.name)
                put(MediaStore.Downloads.MIME_TYPE, mimeType)
                put(MediaStore.Downloads.RELATIVE_PATH, relPath)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }

            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: throw IOException("No se pudo crear la entrada en Descargas.")

            try {
                resolver.openOutputStream(uri)?.use { out ->
                    sourceFile.inputStream().use { input ->
                        input.copyTo(out)
                    }
                } ?: throw IOException("No se pudo escribir en el almacenamiento de Descargas.")

                val publishValues = ContentValues().apply {
                    put(MediaStore.Downloads.IS_PENDING, 0)
                }
                resolver.update(uri, publishValues, null, null)
            } catch (exc: Exception) {
                resolver.delete(uri, null, null)
                throw exc
            }

            var finalName = sourceFile.name
            resolver.query(uri, arrayOf(MediaStore.Downloads.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val idx = cursor.getColumnIndex(MediaStore.Downloads.DISPLAY_NAME)
                    if (idx >= 0) {
                        finalName = cursor.getString(idx) ?: finalName
                    }
                }
            }

            sourceFile.delete()
            return SavedMedia(
                displayPath = "Download/!Download/$finalName",
                contentUri = uri,
                mimeType = mimeType,
                fileName = finalName,
                sizeBytes = sizeBytes,
            )
        }

        @Suppress("DEPRECATION")
        val baseDir = File(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
            "!Download",
        )
        if (!baseDir.exists()) {
            baseDir.mkdirs()
        }

        var target = File(baseDir, sourceFile.name)
        if (target.exists()) {
            val stem = sourceFile.nameWithoutExtension
            val ext = sourceFile.extension
            var counter = 1
            while (target.exists()) {
                val candidateName = if (ext.isNotEmpty()) "$stem ($counter).$ext" else "$stem ($counter)"
                target = File(baseDir, candidateName)
                counter += 1
            }
        }

        sourceFile.copyTo(target, overwrite = false)
        sourceFile.delete()

        MediaScannerConnection.scanFile(
            context,
            arrayOf(target.absolutePath),
            arrayOf(mimeType),
            null,
        )

        val uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            target,
        )

        return SavedMedia(
            displayPath = target.absolutePath,
            contentUri = uri,
            mimeType = mimeType,
            fileName = target.name,
            sizeBytes = sizeBytes,
        )
    }
}
