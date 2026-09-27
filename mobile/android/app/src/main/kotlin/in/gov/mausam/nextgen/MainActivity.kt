package in.gov.mausam.nextgen

import android.Manifest
import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.pm.PackageManager
import android.location.LocationManager
import android.os.Build
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * MainActivity — hosts Flutter and exposes the coarse-location channel used
 * by TASK-061: the app asks for COARSE location only, snaps to the 5 km grid
 * in Dart, and never transmits raw coordinates (DPDP).
 */
class MainActivity : FlutterActivity() {
    private val channelName = "mausam/location"
    private val widgetChannelName = "mausam/home_widget"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "hasCoarsePermission" -> result.success(hasCoarsePermission())
                    "lastCoarseFix" -> result.success(lastCoarseFix())
                    else -> result.notImplemented()
                }
            }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, widgetChannelName)
            .setMethodCallHandler { call, result ->
                if (call.method == "updateSnapshot") {
                    updateHomeWidget(call)
                    result.success(true)
                } else {
                    result.notImplemented()
                }
            }
    }

    /** TASK-076: persist snapshot + redraw every placed widget. */
    private fun updateHomeWidget(call: io.flutter.plugin.common.MethodCall) {
        val prefs = getSharedPreferences(MausamHomeWidgetProvider.PREFS, MODE_PRIVATE)
        prefs.edit()
            .putString(MausamHomeWidgetProvider.KEY_PLACE, call.argument<String>("place"))
            .putFloat(MausamHomeWidgetProvider.KEY_TEMP, (call.argument<Double>("temp_c") ?: 0.0).toFloat())
            .putInt(MausamHomeWidgetProvider.KEY_RAIN, call.argument<Int>("rain_pct") ?: 0)
            .putString(MausamHomeWidgetProvider.KEY_SEVERITY, call.argument<String>("severity"))
            .apply()
        val manager = AppWidgetManager.getInstance(this)
        val ids = manager.getAppWidgetIds(
            ComponentName(this, MausamHomeWidgetProvider::class.java)
        )
        if (ids.isNotEmpty()) {
            MausamHomeWidgetProvider().onUpdate(
                this, manager, ids
            )
        }
    }

    private fun hasCoarsePermission(): Boolean =
        ContextCompat.checkSelfPermission(
            this, Manifest.permission.ACCESS_COARSE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED

    /**
     * Returns the last known passive/network fix truncated to ~0.05° so the
     * platform side ALSO never hands the Dart layer better-than-coarse data.
     * null when no fix or permission missing (UI falls back to saved city).
     */
    private fun lastCoarseFix(): List<Double>? {
        if (!hasCoarsePermission()) return null
        val lm = getSystemService(LOCATION_SERVICE) as LocationManager
        val providers = listOfNotNull(
            if (lm.isProviderEnabled(LocationManager.PASSIVE_PROVIDER)) LocationManager.PASSIVE_PROVIDER else null,
            if (lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) LocationManager.NETWORK_PROVIDER else null,
        )
        for (p in providers) {
            try {
                @Suppress("MissingPermission")
                val loc = lm.getLastKnownLocation(p) ?: continue
                val coarse = { v: Double -> Math.floor(v / 0.05) * 0.05 }
                return listOf(coarse(loc.latitude), coarse(loc.longitude))
            } catch (_: SecurityException) {
                // permission revoked mid-run — fall through
            }
        }
        return null
    }
}
