import 'package:flutter/services.dart';

/// TASK-076 Dart half: writes the latest weather snapshot to the Android
/// home-screen widget. Fire-and-forget after each successful SDUI load;
/// silent no-op on iOS/other platforms (widget is Android-only this phase).
class HomeWidgetService {
  static const _channel = MethodChannel('mausam/home_widget');

  /// [severity] non-null + Extreme/Severe flips the widget red natively.
  static Future<void> updateSnapshot({
    required String place,
    required double tempC,
    required int rainPct,
    String? severity,
  }) async {
    try {
      await _channel.invokeMethod('updateSnapshot', {
        'place': place,
        'temp_c': tempC,
        'rain_pct': rainPct,
        'severity': severity,
      });
    } on MissingPluginException {
      // Not running on Android with the native handler (tests, iOS) — fine.
    } catch (_) {
      // Widget updates must never disturb the app.
    }
  }
}
