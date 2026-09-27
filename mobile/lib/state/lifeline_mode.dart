import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:hive_ce/hive.dart';

import '../sdui/sdui_models.dart';

/// How the takeover was triggered — the demo inspector shows this.
enum LifelineTrigger { disasterCard, manualDemo, fcmPush }

@immutable
class LifelineState {
  final bool active;
  final DisasterProps? alert;
  final LifelineTrigger trigger;
  final DateTime? since;

  const LifelineState({
    required this.active,
    this.alert,
    this.trigger = LifelineTrigger.disasterCard,
    this.since,
  });

  static const initial = LifelineState(active: false);

  LifelineState copyWith({
    bool? active,
    DisasterProps? alert,
    LifelineTrigger? trigger,
    DateTime? since,
  }) {
    return LifelineState(
      active: active ?? this.active,
      alert: alert ?? this.alert,
      trigger: trigger ?? this.trigger,
      since: since ?? this.since,
    );
  }
}

/// TASK-052 brain: the disaster lifeline UI hijack.
///
/// Trigger path is the HONEST production one — the backend composer already
/// pins `disaster_lifeline_card` to position 0 of every SDUI home payload for
/// users inside an active Severe+ CAP polygon (poller → alert store → geofence
/// → gateway). This controller watches each fetched payload; the first time a
/// disaster card appears it raises the takeover (the phone "hijacks" the
/// screen), mirroring what an FCM high-priority push wakes into (TASK-051).
///
/// The jury pitch additionally needs a CONTROLLABLE disaster: [triggerDemo]
/// persists a synthetic Extreme alert in `lifeline_box` (auto-expiring), which
/// overrides polling until acknowledged — so the takeover can be staged
/// offline with the venue Wi-Fi dead.
class LifelineController extends ChangeNotifier {
  LifelineState _state = LifelineState.initial;

  /// Headline the user explicitly acknowledged — suppressed from re-raising
  /// on subsequent polls. A NEW warning (different headline) still hijacks.
  String? _lastAckedHeadline;

  /// Resolves the freshest SDUI home payload (injected by the app shell —
  /// the same repository call the homepage uses, so cache/304 paths apply).
  Future<SduiPayload?> Function()? _fetch;
  Timer? _pollTimer;

  LifelineState get state => _state;
  bool get active => _state.active;
  DisasterProps? get alert => _state.alert;

  static const _boxName = 'lifeline_box';
  static const _demoKey = 'demo_drill_v1';

  /// Starts the watch loop. [fetch] is typically `() => _repo.loadHome(...)`.
  /// The homepage's own fetches feed [recordPayload] directly (no duplicate
  /// network call); this timer re-checks between user refreshes so a new
  /// alert surfaces within [every] even if the user never pulls to refresh.
  void start({
    required Future<SduiPayload?> Function() fetch,
    Duration every = const Duration(seconds: 60),
  }) {
    _fetch = fetch;
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(every, (_) => checkNow());
  }

  /// Forces one watch cycle (also used right after staging a demo drill).
  Future<void> checkNow() async {
    final fetch = _fetch;
    if (fetch == null) {
      // No fetch hook wired yet (fresh boot before the first payload):
      // a persisted, unexpired drill is fully local — still re-raise it.
      await _evaluate(_activeDemoDrill());
      return;
    }
    try {
      final payload = await fetch();
      await recordPayload(payload);
    } catch (_) {
      // Offline poll failure must never crash the watcher; the store keeps
      // the last state and the next tick retries. A staged drill survives:
      // recordPayload/_evaluate re-read the box on every cycle.
      await _evaluate(_activeDemoDrill());
    }
  }

  /// TASK-051 door: an FCM high-priority push wakes the app straight into
  /// Lifeline Mode. Trigger is recorded separately so the inspector can show
  /// push-vs-feed provenance. A push ALWAYS overrides acknowledge-suppression
  /// (official pushes are deliberately re-alerting by design).
  Future<void> recordPush(DisasterProps alert) async {
    _lastAckedHeadline = null;
    _state = LifelineState(
      active: true,
      alert: alert,
      trigger: LifelineTrigger.fcmPush,
      since: DateTime.now(),
    );
    notifyListeners();
  }

  /// Inspect one freshly fetched payload for a pinned disaster card.
  Future<void> recordPayload(SduiPayload? payload) async {
    DisasterProps? found;
    if (payload != null) {
      for (final w in payload.widgets) {
        if (w.type == 'disaster_lifeline_card') {
          found = DisasterProps.tryParse(w.props);
          if (found != null) break;
        }
      }
    }
    await _evaluate(found);
  }

  Future<void> _evaluate(DisasterProps? detected) async {
    final drill = _activeDemoDrill();
    // Staged drill wins over feed detection so the demo always works,
    // even with the venue network fully dead.
    final chosen = drill ?? detected;
    final trigger =
        drill != null ? LifelineTrigger.manualDemo : LifelineTrigger.disasterCard;

    if (chosen == null) {
      if (_state.active) {
        _state = LifelineState.initial;
        notifyListeners();
      }
      return;
    }
    // Already acknowledged by the user → don't re-hijack for the SAME
    // warning (a new/different headline still raises the takeover).
    if (chosen.headline == _lastAckedHeadline) return;
    final unchanged = _state.active && _state.alert?.headline == chosen.headline;
    if (unchanged) return;
    _state = LifelineState(
      active: true,
      alert: chosen,
      trigger: trigger,
      since: DateTime.now(),
    );
    notifyListeners();
  }

  /// Jury demo: stage an Extreme alert for [duration], takeover rises on the
  /// next check. Call [acknowledge] (or tap the exit button) to end it.
  Future<void> triggerDemo({
    String event = 'Cyclone Warning',
    String severity = 'Extreme',
    String headline = 'EXTREME Cyclone Warning — coastal belt (SIMULATED DRILL)',
    String? areaDesc,
    Duration duration = const Duration(minutes: 30),
  }) async {
    // Explicit re-staging is user intent — lift any acknowledge suppression
    // so staging twice (two jury groups) always hijacks again.
    _lastAckedHeadline = null;
    final box = await _box;
    final until = DateTime.now().add(duration).toIso8601String();
    await box.put(
      _demoKey,
      jsonEncode({
        'event': event,
        'severity': severity,
        'headline': headline,
        'area_desc': areaDesc,
        'until': until,
      }),
    );
    // Evaluate immediately so the takeover rises instantly — even fully
    // offline (a staged drill needs no fetch round-trip).
    await _evaluate(_activeDemoDrill());
  }

  /// User acknowledged the takeover — clears a staged drill, drops the
  /// active state, and suppresses re-raising for THIS headline. A different
  /// (new/escalated) warning still hijacks the screen.
  Future<void> acknowledge() async {
    final box = await _box;
    await box.delete(_demoKey);
    _lastAckedHeadline = _state.alert?.headline;
    if (_state.active) {
      _state = LifelineState.initial;
      notifyListeners();
    }
  }

  /// Demo drill still inside its validity window, or null.
  DisasterProps? _activeDemoDrill() {
    final box = Hive.isBoxOpen(_boxName) ? Hive.box<String>(_boxName) : null;
    final raw = box?.get(_demoKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      final json = jsonDecode(raw) as Map<String, dynamic>;
      final until = DateTime.tryParse(json['until']?.toString() ?? '');
      if (until == null || until.isBefore(DateTime.now())) {
        box?.delete(_demoKey); // expired drill self-cleans
        return null;
      }
      final headline = json['headline']?.toString();
      if (headline == null) return null;
      return DisasterProps(
        event: json['event']?.toString() ?? 'Weather Alert',
        severity: json['severity']?.toString() ?? 'Extreme',
        headline: headline,
        areaDesc: json['area_desc']?.toString(),
        safetySteps: const [],
        emergencyNumbers: const [],
      );
    } catch (_) {
      return null;
    }
  }

  Future<Box<String>> get _box async {
    if (Hive.isBoxOpen(_boxName)) return Hive.box<String>(_boxName);
    return Hive.openBox<String>(_boxName);
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }
}
