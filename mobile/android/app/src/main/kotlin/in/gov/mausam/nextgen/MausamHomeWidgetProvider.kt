package `in`.gov.mausam.nextgen

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews

/**
 * TASK-076: 2x2 home-screen widget. The Dart layer writes the latest
 * snapshot (temp, rain %, alert severity) into shared prefs via the
 * home_widget bridge; this provider renders it — flipping to the high-
 * contrast red style during active CAP warnings without opening the app.
 */
class MausamHomeWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        for (id in ids) manager.updateAppWidget(id, buildViews(context))
    }

    private fun buildViews(context: Context): RemoteViews {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val temp = prefs.getFloat(KEY_TEMP, 0f)
        val rain = prefs.getInt(KEY_RAIN, 0)
        val label = prefs.getString(KEY_PLACE, "Mausam") ?: "Mausam"
        val severity = prefs.getString(KEY_SEVERITY, null)
        val disaster = severity == "Extreme" || severity == "Severe"

        val views = RemoteViews(context.packageName, R.layout.mausam_home_widget).apply {
            setTextViewText(R.id.widget_place, label)
            setTextViewText(R.id.widget_temp, "${temp.toInt()}°")
            setTextViewText(
                R.id.widget_sub,
                if (disaster) "$severity ALERT • rain $rain%" else "rain $rain%",
            )
            val bg = if (disaster) 0xFFB71C1C.toInt() else 0xFF0B57D0.toInt()
            setInt(R.id.widget_root, "setBackgroundColor", bg)
        }

        val open = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        views.setOnClickPendingIntent(
            R.id.widget_root,
            PendingIntent.getActivity(
                context, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            ),
        )
        return views
    }

    companion object {
        const val PREFS = "mausam_home_widget"
        const val KEY_TEMP = "temp_c"
        const val KEY_RAIN = "rain_pct"
        const val KEY_PLACE = "place"
        const val KEY_SEVERITY = "alert_severity"
    }
}
