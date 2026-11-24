package com.juancorporation.exclaimdownload

import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Environment
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.Locale
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.Executors
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

class DownloadManagerEngine(private val app: DownloadApp) {

    private val executor = Executors.newFixedThreadPool(2)
    private val jobs = ConcurrentHashMap<String, JobRecord>()
    private val savedUriByPath = ConcurrentHashMap<String, Pair<Uri, String>>()
    private val activeDownloads = AtomicInteger(0)

    private val tempSuffixes = setOf("part", "ytdl", "temp", "tmp")
    private val imageSuffixes = setOf("webp", "jpg", "jpeg", "png", "gif")
    private val metaSuffixes = setOf("json", "description", "xml")

    private val sizeLineRegex = Regex("""of\s+~?\s*([\d.]+)\s*(GiB|MiB|KiB|GB|MB|KB|B)""", RegexOption.IGNORE_CASE)
    private val speedLineRegex = Regex("""at\s+([\d.]+)\s*(GiB|MiB|KiB|GB|MB|KB|B)/s""", RegexOption.IGNORE_CASE)

    data class JobRequest(
        val url: String,
        val mode: String,
        val height: Int?,
        val container: String,
        val audioFormat: String,
        val audioBitrate: Int,
        val embedMetadata: Boolean,
        val titleHint: String?,
    )

    class JobRecord(
        val jobId: String,
        val req: JobRequest,
        val jobDir: File,
        val qualityLabel: String,
        val createdAt: Double,
    ) {
        @Volatile var status: String = "queued"
        @Volatile var stage: String = "En cola..."
        @Volatile var percent: Double = 0.0
        @Volatile var speed: Double? = null
        @Volatile var eta: Long? = null
        @Volatile var downloadedBytes: Long? = null
        @Volatile var totalBytes: Long? = null
        @Volatile var filename: String? = null
        @Volatile var filesize: Long? = null
        @Volatile var savedPath: String? = null
        @Volatile var savedUri: Uri? = null
        @Volatile var savedMime: String? = null
        @Volatile var title: String? = req.titleHint
        @Volatile var error: String? = null
        val cancelled = AtomicBoolean(false)
        val subscribers = CopyOnWriteArrayList<LinkedBlockingQueue<String>>()

        fun toJson(): JSONObject = JSONObject().apply {
            put("job_id", jobId)
            put("status", status)
            put("stage", stage)
            put("percent", (percent * 10.0).toInt() / 10.0)
            put("speed", speed ?: JSONObject.NULL)
            put("eta", eta ?: JSONObject.NULL)
            put("downloaded_bytes", downloadedBytes ?: JSONObject.NULL)
            put("total_bytes", totalBytes ?: JSONObject.NULL)
            put("filename", filename ?: JSONObject.NULL)
            put("filesize", filesize ?: JSONObject.NULL)
            put("saved_path", savedPath ?: JSONObject.NULL)
            put("title", title ?: JSONObject.NULL)
            put("mode", req.mode)
            put("quality_label", qualityLabel)
            put("error", error ?: JSONObject.NULL)
            put("created_at", createdAt)
        }
    }

    fun createJob(req: JobRequest): JobRecord {
        val jobId = UUID.randomUUID().toString().replace("-", "").take(12)
        val tempRoot = File(app.cacheDir, "temp_downloads").apply { mkdirs() }
        val jobDir = File(tempRoot, jobId).apply { mkdirs() }

        val qualityLabel = if (req.mode == "video") {
            val res = if (req.height != null) "${req.height}p" else "Mejor"
            "$res · ${req.container.uppercase(Locale.ROOT)}"
        } else {
            if (req.audioFormat in setOf("flac", "wav")) {
                "${req.audioFormat.uppercase(Locale.ROOT)} · Sin pérdida"
            } else {
                "${req.audioFormat.uppercase(Locale.ROOT)} · ${req.audioBitrate} kbps"
            }
        }

        val job = JobRecord(
            jobId = jobId,
            req = req,
            jobDir = jobDir,
            qualityLabel = qualityLabel,
            createdAt = System.currentTimeMillis() / 1000.0,
        )
        jobs[jobId] = job
        executor.submit { runJob(job) }
        return job
    }

    fun getJob(jobId: String): JobRecord? = jobs[jobId]

    fun listRecentJobs(limit: Int = 15): JSONArray {
        val sorted = jobs.values.sortedByDescending { it.createdAt }.take(limit)
        return JSONArray().apply {
            sorted.forEach { put(it.toJson()) }
        }
    }

    fun subscribe(jobId: String): Pair<LinkedBlockingQueue<String>, JSONObject>? {
        val job = jobs[jobId] ?: return null
        val queue = LinkedBlockingQueue<String>(64)
        val snapshot = job.toJson()
        if (job.status !in TERMINAL_STATUSES) {
            job.subscribers.add(queue)
        }
        return queue to snapshot
    }

    fun unsubscribe(jobId: String, queue: LinkedBlockingQueue<String>) {
        jobs[jobId]?.subscribers?.remove(queue)
    }

    fun cancelJob(jobId: String): JobRecord? {
        val job = jobs[jobId] ?: return null
        if (job.status in TERMINAL_STATUSES) return job

        job.cancelled.set(true)
        if (job.status == "queued") {
            job.status = "cancelled"
            job.stage = "Descarga cancelada"
            job.jobDir.deleteRecursively()
            notifySubscribers(job)
        } else {
            job.stage = "Cancelando descarga..."
            notifySubscribers(job)
            runCatching { YoutubeDL.getInstance().destroyProcessById(jobId) }
        }
        return job
    }

    fun openSavedFile(path: String): Boolean {
        val entry = savedUriByPath[path] ?: return false
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(entry.first, entry.second)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
        }
        app.startActivity(intent)
        return true
    }

    fun openDownloadsFolder(): Boolean {
        val viewDownloads = Intent(DownloadManager.ACTION_VIEW_DOWNLOADS).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        val started = runCatching { app.startActivity(viewDownloads) }.isSuccess
        if (started) return true

        val fallbackDir = File(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
            "!Download",
        )
        val fallbackIntent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(Uri.fromFile(fallbackDir), "resource/folder")
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        return runCatching { app.startActivity(fallbackIntent) }.isSuccess
    }

    private fun notifySubscribers(job: JobRecord) {
        val payload = job.toJson().toString()
        val isTerminal = job.status in TERMINAL_STATUSES
        for (queue in job.subscribers) {
            if (queue.remainingCapacity() == 0) {
                queue.poll()
            }
            queue.offer(payload)
        }
        if (isTerminal) {
            job.subscribers.clear()
        }
    }

    private fun toBytes(value: Double, unit: String): Long {
        val mult = when (unit.lowercase(Locale.ROOT)) {
            "gib", "gb" -> 1024.0 * 1024.0 * 1024.0
            "mib", "mb" -> 1024.0 * 1024.0
            "kib", "kb" -> 1024.0
            else -> 1.0
        }
        return (value * mult).toLong()
    }

    private fun runJob(job: JobRecord) {
        if (job.cancelled.get() || job.status == "cancelled") {
            job.jobDir.deleteRecursively()
            return
        }

        activeDownloads.incrementAndGet()
        val displayTitle = job.title ?: "!Download"
        var lastNotifyMs = 0L

        try {
            val engineStatus = runBlocking { app.ensureEngineReady() }
            if (!engineStatus.ready) {
                throw IllegalStateException(engineStatus.error ?: "El motor multimedia no pudo inicializarse.")
            }

            job.status = "downloading"
            job.stage = "Preparando descarga..."
            job.percent = 0.0
            notifySubscribers(job)
            DownloadForegroundService.updateProgress(app, displayTitle, job.stage, 0, true)

            val request = YoutubeDLRequest(job.req.url).apply {
                addOption("--no-playlist")
                addOption("--playlist-items", "1")
                addOption("--socket-timeout", "25")
                addOption("--retries", "3")
                addOption("--fragment-retries", "3")
                addOption("--no-mtime")
                addOption("-o", "${job.jobDir.absolutePath}/%(title).100B.%(ext)s")

                if (job.req.mode == "video") {
                    addOption("-f", MediaParser.buildVideoFormatSelector(job.req.height, job.req.container))
                    addOption("--merge-output-format", job.req.container)
                } else {
                    addOption("-f", "bestaudio/best")
                    addOption("-x")
                    addOption("--audio-format", job.req.audioFormat)
                    val q = if (job.req.audioFormat in setOf("flac", "wav")) "0" else "${job.req.audioBitrate}K"
                    addOption("--audio-quality", q)
                }

                if (job.req.embedMetadata) {
                    addOption("--add-metadata")
                }
            }

            YoutubeDL.getInstance().execute(request, job.jobId) { progress, etaInSeconds, line ->
                if (job.cancelled.get()) return@execute

                val lower = line.lowercase(Locale.ROOT)
                when {
                    "[merger]" in lower -> {
                        job.status = "processing"
                        job.stage = "Uniendo video y audio en ${job.req.container.uppercase(Locale.ROOT)}..."
                        job.percent = 99.0
                        job.eta = 0L
                        job.speed = null
                    }
                    "[extractaudio]" in lower -> {
                        job.status = "processing"
                        job.stage = "Convirtiendo audio a ${job.req.audioFormat.uppercase(Locale.ROOT)}..."
                        job.percent = 99.0
                        job.eta = 0L
                        job.speed = null
                    }
                    "[metadata]" in lower -> {
                        job.status = "processing"
                        job.stage = "Escribiendo metadatos..."
                        job.percent = 99.0
                        job.eta = 0L
                        job.speed = null
                    }
                    progress >= 0f -> {
                        job.status = "downloading"
                        job.stage = if (job.req.mode == "video") "Descargando video y audio..." else "Descargando audio..."
                        job.percent = progress.toDouble().coerceIn(0.0, 99.0)
                        if (etaInSeconds >= 0) {
                            job.eta = etaInSeconds
                        }
                        sizeLineRegex.find(line)?.let { m ->
                            val num = m.groupValues[1].toDoubleOrNull()
                            val unit = m.groupValues[2]
                            if (num != null) {
                                val tot = toBytes(num, unit)
                                job.totalBytes = tot
                                job.downloadedBytes = (tot * (job.percent / 100.0)).toLong()
                            }
                        }
                        speedLineRegex.find(line)?.let { m ->
                            val num = m.groupValues[1].toDoubleOrNull()
                            val unit = m.groupValues[2]
                            if (num != null) {
                                job.speed = toBytes(num, unit).toDouble()
                            }
                        }
                    }
                }

                val now = System.currentTimeMillis()
                if (now - lastNotifyMs >= 200L || job.status == "processing") {
                    lastNotifyMs = now
                    notifySubscribers(job)
                    DownloadForegroundService.updateProgress(
                        app,
                        displayTitle,
                        job.stage,
                        job.percent.toInt(),
                        job.status == "processing" || job.percent <= 0.0,
                    )
                }
            }

            if (job.cancelled.get()) {
                job.status = "cancelled"
                job.stage = "Descarga cancelada"
                job.speed = null
                job.eta = null
                job.jobDir.deleteRecursively()
                notifySubscribers(job)
                return
            }

            val outputFile = findOutputFile(job.jobDir)
            job.stage = "Guardando en Descargas..."
            job.status = "processing"
            job.percent = 99.5
            notifySubscribers(job)

            val saved = MediaStoreSaver.saveToDownloads(app, outputFile)
            savedUriByPath[saved.displayPath] = saved.contentUri to saved.mimeType
            job.jobDir.deleteRecursively()

            job.status = "completed"
            job.stage = "¡Guardado en Descargas!"
            job.percent = 100.0
            job.speed = null
            job.eta = 0L
            job.filename = saved.fileName
            job.filesize = saved.sizeBytes
            job.savedPath = saved.displayPath
            job.savedUri = saved.contentUri
            job.savedMime = saved.mimeType
            notifySubscribers(job)

            DownloadForegroundService.postCompletedNotification(
                app,
                job.title ?: saved.fileName,
                job.qualityLabel,
                saved.contentUri,
                saved.mimeType,
            )
        } catch (exc: Exception) {
            job.jobDir.deleteRecursively()
            if (job.cancelled.get()) {
                job.status = "cancelled"
                job.stage = "Descarga cancelada"
                job.speed = null
                job.eta = null
            } else {
                job.status = "error"
                job.stage = "Error en la descarga"
                job.speed = null
                job.eta = null
                job.error = MediaParser.translateYtDlpError(exc.message)
            }
            notifySubscribers(job)
        } finally {
            if (activeDownloads.decrementAndGet() <= 0) {
                DownloadForegroundService.stop(app)
            }
        }
    }

    private fun findOutputFile(jobDir: File): File {
        val candidates = jobDir.listFiles()?.filter { file ->
            if (!file.isFile) return@filter false
            val ext = file.extension.lowercase(Locale.ROOT)
            val name = file.name.lowercase(Locale.ROOT)
            ext !in tempSuffixes &&
                ext !in imageSuffixes &&
                ext !in metaSuffixes &&
                !name.endsWith(".annotations.xml")
        }.orEmpty()

        return candidates.maxByOrNull { it.length() }
            ?: throw IllegalStateException("No se encontró el archivo resultante tras la descarga.")
    }

    companion object {
        val TERMINAL_STATUSES = setOf("completed", "error", "cancelled")
    }
}
