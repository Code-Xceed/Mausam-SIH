import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive_ce/hive.dart';
import 'package:mausam_nextgen/l10n/condition_glyphs.dart';
import 'package:mausam_nextgen/l10n/language_store.dart';
import 'package:mausam_nextgen/push/mausam_push.dart';
import 'package:mausam_nextgen/search/search_service.dart';
import 'package:mausam_nextgen/sdui/sdui_models.dart';
import 'package:mausam_nextgen/state/lifeline_mode.dart';
import 'package:mausam_nextgen/storage/hive_manager.dart';

/// Phase 8/9 mobile acceptance: push takeover (TASK-051 logic), language
/// store (TASK-063), glyphs (TASK-067), Hive purge (TASK-072), and the
/// 500-keystroke search chaos test (TASK-068, mobile half).

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory scratch;

  setUpAll(() async {
    scratch = await Directory.systemTemp.createTemp('mausam_phase8_9_test');
    Hive.init(scratch.path);
  });

  tearDownAll(() async {
    try {
      await Hive.close();
    } catch (_) {}
    try {
      await scratch.delete(recursive: true);
    } catch (_) {}
  });

  group('push → lifeline takeover (TASK-051 logic half)', () {
    test('parses a CAP-derived FCM payload and raises the takeover', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      final handler = MausamPushHandler(c);

      final ok = await handler.handleData({
        'identifier': 'cap-1',
        'event': 'Cyclone Warning',
        'severity': 'Extreme',
        'headline': 'Extreme cyclone approaching coast',
        'area_desc': 'Konkan belt',
      });

      expect(ok, isTrue);
      expect(c.active, isTrue);
      expect(c.state.trigger, LifelineTrigger.fcmPush);
      expect(c.alert!.severity, 'Extreme');
    });

    test('payload without headline is rejected', () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      expect(MausamPushHandler.parse({'severity': 'Extreme'}), isNull);
      expect(await MausamPushHandler(c).handleData({'severity': 'Extreme'}), isFalse);
      expect(c.active, isFalse);
    });

    test('push overrides acknowledge-suppression (re-alerting by design)',
        () async {
      final c = LifelineController();
      addTearDown(c.dispose);
      await c.recordPayload(_payloadWith('Same warning'));
      await c.acknowledge();
      final handler = MausamPushHandler(c);

      await handler.handleData({
        'event': 'Cyclone Warning',
        'severity': 'Severe',
        'headline': 'Same warning',
      });
      expect(c.active, isTrue,
          reason: 'an OFFICIAL push must always re-hijack');
    });
  });

  group('language store (TASK-063)', () {
    test('defaults to English and persists a switch + offline bundle',
        () async {
      final store = LanguageStore();
      expect(await store.load(), 'en');

      await store.save('hi');
      expect(await store.load(), 'hi');

      expect(await store.loadBundle('hi'), isNull); // nothing cached yet
      await store.saveBundle('hi', {
        'strings': {'app_title': 'मौसम नेक्स्ट-जेन'},
      });
      final bundle = await store.loadBundle('hi');
      expect(bundle!['strings']['app_title'], 'मौसम नेक्स्ट-जेन');
    });
  });

  group('condition glyphs (TASK-067)', () {
    test('every condition has a DISTINCT glyph', () {
      final conditions = [
        'clear', 'partly_cloudy', 'cloudy', 'fog', 'haze',
        'drizzle', 'rain', 'thunderstorm', 'hail', 'snow',
      ];
      final glyphs = conditions.map(ConditionGlyphs.glyphFor).toSet();
      expect(glyphs.length, conditions.length,
          reason: 'low-literacy users must distinguish conditions by SHAPE');
    });

    test('severity glyphs escalate visually (shape AND color)', () {
      final (_, extremeColor) = ConditionGlyphs.severityGlyph('Extreme');
      final (_, severeColor) = ConditionGlyphs.severityGlyph('Severe');
      final (_, moderateColor) = ConditionGlyphs.severityGlyph('Moderate');
      expect(extremeColor, isNot(severeColor));
      expect(severeColor, isNot(moderateColor));
      expect(ConditionGlyphs.semanticLabel('rain'), contains('Rain'));
    });
  });

  group('DPDP purge (TASK-072 mobile half)', () {
    test('purgeAll wipes every box including lifeline_box', () async {
      await HiveManager.init();
      final lifeline = await Hive.openBox<String>('lifeline_box');
      await lifeline.put('demo_drill_v1', '{"headline":"x"}');
      await (Hive.box<String>('persona_box'))
          .put('active_personas', 'health,commuter');

      await HiveManager.purgeAll();

      expect(lifeline.get('demo_drill_v1'), isNull);
      expect(Hive.box<String>('persona_box').get('active_personas'), isNull);
      expect(Hive.box<String>('favorites_box').isEmpty, isTrue);
    });
  });

  group('search chaos — 500 rapid keystrokes (TASK-068 mobile half)', () {
    test('debounced service survives 500 rapid inputs without error',
        () async {
      final service = SearchService();
      service.start(); // gazetteer defaults to empty-until-loaded: safe
      var emissions = 0;
      var errored = false;
      final sub = service.results.listen(
        (_) => emissions++,
        onError: (_) => errored = true,
      );

      // Simulate the monkey test: 500 rapid async keystrokes.
      for (var i = 0; i < 500; i++) {
        service.submit('mumb${String.fromCharCode(97 + (i % 26))}');
      }
      await Future<void>.delayed(const Duration(milliseconds: 700));
      await sub.cancel();
      service.dispose();

      expect(errored, isFalse, reason: 'no error may escape the stream');
      // The 500ms debounce collapses the storm into at most a few searches.
      expect(emissions, lessThanOrEqualTo(4),
          reason: 'debounce must collapse the keystroke storm');
    });
  });
}

SduiPayload _payloadWith(String headline) {
  return SduiPayload(
    schemaVersion: 'v1',
    displayName: 'Mumbai',
    activePersonas: const [],
    sourcesUsed: const [],
    stale: false,
    widgets: [
      SduiWidget(
        id: 'd',
        type: 'disaster_lifeline_card',
        props: {
          'event': 'Cyclone Warning',
          'severity': 'Severe',
          'headline': headline,
        },
        priority: 99,
      ),
    ],
  );
}
