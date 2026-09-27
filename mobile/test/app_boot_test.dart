import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_ce/hive.dart';
import 'package:mausam_nextgen/audio/suno_mausam.dart';
import 'package:mausam_nextgen/main.dart';
import 'package:mausam_nextgen/push/home_widget_service.dart';
import 'package:mausam_nextgen/screens/onboarding_screen.dart';
import 'package:mausam_nextgen/state/permissions.dart';

/// Compilation + boot smoke: imports the app entrypoint (and the platform-
/// channel services no other test references), so `flutter test` compiles
/// the WHOLE lib tree in CI — icon-name typos and API drift in lib-only
/// files fail here instead of at demo time.
///
/// The boot test pumps HomeGate down the FIRST-LAUNCH path (no saved
/// personas) → onboarding renders. No network, no plugin calls beyond the
/// stubbed channels below.

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory scratch;

  setUpAll(() async {
    scratch = await Directory.systemTemp.createTemp('mausam_boot_test');
    Hive.init(scratch.path);
    await Hive.openBox<String>('persona_box');

    // Stub every platform channel touched on the boot path.
    for (final ch in const ['mausam/location', 'mausam/home_widget']) {
      TestWidgetsFlutterBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(MethodChannel(ch), (call) async => null);
    }
  });

  tearDownAll(() async {
    try {
      if (Hive.isBoxOpen('persona_box')) await Hive.box<String>('persona_box').close();
    } catch (_) {}
    try {
      await scratch.delete(recursive: true);
    } catch (_) {}
  });

  test('app graph compiles and entrypoints are importable', () {
    // Referencing public symbols forces compilation of their libraries.
    expect(MausamApp, isNotNull);
    expect(HomeWidgetService, isNotNull);
    expect(SunoMausam.instance, isNotNull);
    expect(PermissionsHelper, isNotNull);
  });

  testWidgets('MausamApp boots to the onboarding gate (first launch)',
      (tester) async {
    await tester.pumpWidget(const MausamApp());
    await tester.pump(const Duration(milliseconds: 50));
    await tester.pump(const Duration(milliseconds: 50));

    // First launch (no saved personas) → onboarding screen renders.
    expect(find.byType(Navigator), findsOneWidget);
    expect(find.byType(OnboardingScreen), findsOneWidget);
  });
}
