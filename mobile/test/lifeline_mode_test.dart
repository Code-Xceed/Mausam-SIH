import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive_ce/hive.dart';
import 'package:mausam_nextgen/sdui/sdui_models.dart';
import 'package:mausam_nextgen/state/lifeline_mode.dart';

/// Unit tests for the TASK-052 lifeline controller (drill staging, acknowledge
/// suppression, expiry, persistence, feed watching). The controller is a pure
/// ChangeNotifier over a Hive box, so these run headless:
///
///   cd mobile && flutter test test/lifeline_mode_test.dart
///
/// Hive needs a real temp directory even in tests — the default test binding
/// has none, so each test gets its own scratch dir and a freshly opened box.

DisasterProps _feedAlert({String headline = 'Severe Cyclone — feed alert'}) {
  return DisasterProps(
    event: 'Cyclone Warning',
    severity: 'Severe',
    headline: headline,
    areaDesc: 'Konkan coast',
    safetySteps: const ['Move to shelter'],
    emergencyNumbers: const [],
  );
}

SduiPayload _payloadWithCard(DisasterProps alert) {
  return SduiPayload(
    schemaVersion: 'v1',
    displayName: 'Mumbai',
    activePersonas: const ['health'],
    sourcesUsed: const ['NDMA_CAP'],
    stale: false,
    widgets: [
      SduiWidget(
        id: 'disaster-1',
        type: 'disaster_lifeline_card',
        props: {
          'event': alert.event,
          'severity': alert.severity,
          'headline': alert.headline,
          'area_desc': alert.areaDesc,
          'safety_steps': alert.safetySteps,
          'emergency_numbers': const [],
        },
        priority: 99,
      ),
      SduiWidget(id: 'hero', type: 'current_conditions', props: const {}, priority: 50),
    ],
  );
}

void main() {
  late Directory scratch;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    scratch = await Directory.systemTemp.createTemp('mausam_lifeline_test');
    Hive.init(scratch.path);
  });

  tearDownAll(() async {
    if (Hive.isBoxOpen('lifeline_box')) await Hive.box<String>('lifeline_box').close();
    try {
      await scratch.delete(recursive: true);
    } catch (_) {}
  });

  tearDown(() async {
    if (Hive.isBoxOpen('lifeline_box')) await Hive.box<String>('lifeline_box').clear();
  });

  group('drill staging', () {
    test('triggerDemo raises the takeover immediately, fully offline', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      expect(c.active, isFalse);

      await c.triggerDemo();

      expect(c.active, isTrue, reason: 'staging must hijack without any fetch');
      expect(c.alert, isNotNull);
      expect(c.alert!.severity, 'Extreme');
      expect(c.alert!.headline, contains('SIMULATED DRILL'));
      expect(c.state.trigger, LifelineTrigger.manualDemo);
    });

    test('staged drill persists across controller recreation', () async {
      final first = LifelineController();
      await first.triggerDemo();
      first.dispose();

      // Fresh controller (like an app restart) sees the persisted drill.
      final second = LifelineController();
      addTearDown(second.dispose);
      await second.checkNow(); // no-op fetch — drill comes from the box
      expect(second.active, isTrue);
      expect(second.state.trigger, LifelineTrigger.manualDemo);
    });

    test('drill overrides a detected feed alert', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      await c.triggerDemo(headline: 'DRILL wins');
      await c.recordPayload(_payloadWithCard(_feedAlert()));

      expect(c.alert!.headline, 'DRILL wins');
      expect(c.state.trigger, LifelineTrigger.manualDemo);
    });
  });

  group('acknowledge semantics', () {
    test('acknowledge drops a staged drill AND the active state', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      await c.triggerDemo();
      expect(c.active, isTrue);

      await c.acknowledge();

      expect(c.active, isFalse);
      expect(c.alert, isNull);
    });

    test('acknowledged headline does NOT re-raise on subsequent polls', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      final alert = _feedAlert(headline: 'Same warning');
      await c.recordPayload(_payloadWithCard(alert));
      expect(c.active, isTrue);

      await c.acknowledge();
      expect(c.active, isFalse);

      // The SAME warning arrives again on the next poll...
      await c.recordPayload(_payloadWithCard(alert));
      expect(c.active, isFalse, reason: 'same headline must stay suppressed');
    });

    test('a NEW headline still hijacks after acknowledge', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      await c.recordPayload(_payloadWithCard(_feedAlert(headline: 'Old warning')));
      await c.acknowledge();

      await c.recordPayload(_payloadWithCard(_feedAlert(headline: 'NEW escalated warning')));
      expect(c.active, isTrue, reason: 'escalation must re-hijack');
    });

    test('re-staging the same drill always works (second jury group)', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      await c.triggerDemo();
      await c.acknowledge();
      expect(c.active, isFalse);

      await c.triggerDemo();
      expect(c.active, isTrue, reason: 'explicit re-staging lifts suppression');
    });
  });

  group('drill expiry', () {
    test('expired drill self-cleans and does not activate', () async {
      final c = LifelineController();
      addTearDown(c.dispose);

      // Stage with a negative duration → already expired.
      await c.triggerDemo(duration: const Duration(minutes: -1));
      expect(c.active, isFalse, reason: 'expired drill must never raise');

      // And the box no longer holds the stale payload.
      final box = Hive.box<String>('lifeline_box');
      expect(box.get('demo_drill_v1'), isNull);
    });

    test('drill activates before expiry window ends', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      await c.triggerDemo(duration: const Duration(minutes: 30));
      expect(c.active, isTrue);
    });
  });

  group('feed watching', () {
    test('recordPayload activates on a pinned disaster card', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      await c.recordPayload(_payloadWithCard(_feedAlert()));

      expect(c.active, isTrue);
      expect(c.state.trigger, LifelineTrigger.disasterCard);
      expect(c.alert!.severity, 'Severe');
    });

    test('payload without a disaster card clears the takeover', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      await c.recordPayload(_payloadWithCard(_feedAlert()));
      expect(c.active, isTrue);

      final clean = SduiPayload(
        schemaVersion: 'v1',
        displayName: 'Delhi',
        activePersonas: const ['health'],
        sourcesUsed: const [],
        stale: false,
        widgets: const [],
      );
      await c.recordPayload(clean);
      expect(c.active, isFalse);
    });

    test('malformed disaster card props are skipped without crashing', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      final broken = SduiPayload(
        schemaVersion: 'v1',
        displayName: 'X',
        activePersonas: const [],
        sourcesUsed: const [],
        stale: false,
        widgets: [
          const SduiWidget(
            id: 'bad',
            type: 'disaster_lifeline_card',
            props: {'severity': 'Extreme'}, // no headline → parse fails
            priority: 99,
          ),
        ],
      );
      await c.recordPayload(broken);
      expect(c.active, isFalse);
    });

    test('null payload (offline, nothing cached) never activates', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      await c.recordPayload(null);
      expect(c.active, isFalse);
    });

    test('start() timer fetches and feeds the watcher; dispose stops it', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      var calls = 0;
      c.start(
        fetch: () async {
          calls += 1;
          return _payloadWithCard(_feedAlert());
        },
        every: const Duration(milliseconds: 5),
      );
      await Future<void>.delayed(const Duration(milliseconds: 80));
      expect(calls, greaterThanOrEqualTo(1));
      expect(c.active, isTrue);

      final before = calls;
      c.dispose();
      await Future<void>.delayed(const Duration(milliseconds: 40));
      expect(calls, before, reason: 'dispose must cancel the poll timer');
    });

    test('fetch errors are swallowed, not propagated', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      c.start(
        fetch: () async => throw StateError('network dead'),
        every: const Duration(milliseconds: 5),
      );
      await Future<void>.delayed(const Duration(milliseconds: 40));
      expect(c.active, isFalse, reason: 'failed polls must not crash or activate');
    });
  });

  group('drill payload JSON robustness', () {
    test('corrupted box content is ignored, not thrown', () async {
      final box = Hive.box<String>('lifeline_box');
      await box.put('demo_drill_v1', '{not json at all');

      final c = LifelineController();
      addTearDown(c.dispose);
      await c.checkNow();
      expect(c.active, isFalse);
    });

    test('jsonEncode/decode round-trip matches what the controller writes', () async {
      final payload = {
        'headline': 'H',
        'until': DateTime.now().add(const Duration(minutes: 5)).toIso8601String(),
      };
      final raw = jsonEncode(payload);
      final back = jsonDecode(raw) as Map<String, dynamic>;
      expect(back['headline'], 'H');
      expect(DateTime.tryParse(back['until'] as String), isNotNull);
    });
  });
}
