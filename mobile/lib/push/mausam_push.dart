import '../sdui/sdui_models.dart';
import '../state/lifeline_mode.dart';

/// TASK-051 logic half: FCM high-priority data-payload → Lifeline takeover.
///
/// Android delivers an FCM `data` message to the Dart isolate even when the
/// app is backgrounded (priority HIGH + ttl 0 from the backend dispatcher,
/// TASK-050). This handler converts that payload into a [DisasterProps] and
/// raises the lifeline takeover through the SAME controller the in-feed card
/// uses — one code path, two doors.
///
/// Native wiring (deployment-specific, documented in docs/BACKUP_DEPLOY.md):
///   1. `firebase_messaging` plugin + google-services.json (Firebase project)
///   2. background handler: `FirebaseMessaging.onBackgroundMessage(...)`
///      calls [MausamPushHandler.handleData]
///   3. WorkManager expedited worker (android/.../AlertWorker.kt) plays the
///      alert tone + shows the full-screen-intent notification under Doze.
class MausamPushHandler {
  final LifelineController lifeline;

  MausamPushHandler(this.lifeline);

  /// Parse a CAP-derived FCM data payload. Expected keys (matches the
  /// backend dispatcher's message shape):
  ///   identifier, event, severity, headline, area_desc, expires
  static DisasterProps? parse(Map<String, dynamic> data) {
    final headline = data['headline']?.toString();
    if (headline == null || headline.isEmpty) return null;
    return DisasterProps(
      event: data['event']?.toString() ?? 'Weather Alert',
      severity: data['severity']?.toString() ?? 'Severe',
      headline: headline,
      areaDesc: data['area_desc']?.toString(),
      safetySteps: ((data['safety_steps'] as List?) ?? const [])
          .map((e) => e.toString())
          .toList(),
      emergencyNumbers: const [
        EmergencyContact(label: 'National Emergency', number: '112'),
        EmergencyContact(label: 'NDMA Helpline', number: '1078'),
      ],
    );
  }

  /// Entry point from the FCM background isolate / WorkManager callback.
  Future<bool> handleData(Map<String, dynamic> data) async {
    final props = parse(data);
    if (props == null) return false;
    await lifeline.recordPush(props);
    return true;
  }
}
