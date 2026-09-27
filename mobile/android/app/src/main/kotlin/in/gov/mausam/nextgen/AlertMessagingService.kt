package in.gov.mausam.nextgen

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.RingtoneManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.work.BackoffPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.Data as WorkData
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import java.util.concurrent.TimeUnit

/**
 * TASK-051: receives the backend dispatcher's high-priority CAP pushes
 * (priority HIGH, ttl 0 — TASK-050) and wakes the user even under Doze:
 *
 *  1. Immediate high-priority notification on the dedicated disaster channel
 *     (max importance, alert tone, full-screen intent on Android 10+).
 *  2. An EXPEDITED WorkManager job re-verifies + re-alerts within the Doze
 *     maintenance window if the notification was deferred — the "sleeping
 *     phone on the table still sounds" acceptance path.
 *
 * The Dart side receives the same data payload via the plugin's background
 * isolate and raises the Lifeline takeover (mausam_push.dart).
 */
class AlertMessagingService : FirebaseMessagingService() {

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        val severity = data["severity"] ?: return
        if (severity !in setOf("Extreme", "Severe")) return // disaster-only wake

        val headline = data["headline"] ?: "Official weather warning"
        val event = data["event"] ?: "Weather Alert"

        postDisasterNotification(event, headline, data)
        scheduleDozeSafeRealert(data)
    }

    override fun onNewToken(token: String) {
        // Forwarded to the Dart layer via the plugin's token stream; the app
        // registers topic subscriptions per coarse geohash cell there.
        super.onNewToken(token)
    }

    private fun postDisasterNotification(event: String, headline: String, data: Map<String, String>) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Disaster alerts (Lifeline)",
                    NotificationManager.IMPORTANCE_MAX,
                ).apply {
                    description = "Official NDMA/IMD CAP warnings for your area"
                    enableVibration(true)
                    setSound(
                        RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM),
                        null,
                    )
                    setBypassDnd(false)
                }
            )
        }

        val tap = Intent(this, MainActivity::class.java).apply {
            action = "in.gov.mausam.nextgen.LIFELINE_TAP"
            putExtra("identifier", data["identifier"])
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pending = PendingIntent.getActivity(
            this, 0, tap,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val notif = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("$event — ${data["severity"]}")
            .setContentText(headline)
            .setStyle(NotificationCompat.BigTextStyle().bigText(headline))
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setOngoing(true) // persistent lockscreen banner
            .setAutoCancel(false)
            .setContentIntent(pending)
            .apply {
                if (Build.VERSION.SDK_INT >= 29) {
                    setFullScreenIntent(pending, true) // heads-up takeover
                }
            }
            .build()

        nm.notify(NOTIF_ID, notif)
    }

    /** Doze backstop: expedited worker re-raises if the device slept through. */
    private fun scheduleDozeSafeRealert(data: Map<String, String>) {
        val request = OneTimeWorkRequestBuilder<AlertWorker>()
            .setInputData(WorkData.Builder().apply {
                data.forEach { (k, v) -> putString(k, v) }
            }.build())
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .setBackoffCriteria(BackoffPolicy.LINEAR, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(this).enqueueUniqueWork(
            "mausam-alert-realert",
            ExistingWorkPolicy.REPLACE,
            request,
        )
    }

    companion object {
        const val CHANNEL_ID = "mausam_disaster_alerts"
        const val NOTIF_ID = 26076
    }
}

/** Expedited Doze-path worker: re-posts the alert + re-wakes the app. */
class AlertWorker(ctx: Context, params: WorkerParameters) : Worker(ctx, params) {
    override fun doWork(): Result {
        val headline = inputData.getString("headline") ?: return Result.success()
        val event = inputData.getString("event") ?: "Weather Alert"
        val nm = applicationContext.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val notif = NotificationCompat.Builder(applicationContext, AlertMessagingService.CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("$event — Doze re-alert")
            .setContentText(headline)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .build()
        nm.notify(AlertMessagingService.NOTIF_ID + 1, notif)
        return Result.success()
    }
}
