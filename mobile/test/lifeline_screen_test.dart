import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mausam_nextgen/safety/lifeline_screen.dart';
import 'package:mausam_nextgen/sdui/sdui_models.dart';

/// Widget tests for the Disaster Lifeline takeover (TASK-052). The checklist
/// push-through loads the bundled NDMA asset, which `flutter test` serves
/// from pubspec-declared assets.
///
///   cd mobile && flutter test test/lifeline_screen_test.dart

const _extremeAlert = DisasterProps(
  event: 'Cyclone Warning',
  severity: 'Extreme',
  headline: 'EXTREME Cyclone Warning — coastal belt (SIMULATED DRILL)',
  areaDesc: 'Mumbai coastal belt',
  safetySteps: ['Move to the nearest shelter', 'Charge phones and power banks'],
  emergencyNumbers: [
    EmergencyContact(label: 'National Emergency', number: '112'),
    EmergencyContact(label: 'NDMA Helpline', number: '1078'),
  ],
);

void main() {
  testWidgets('renders hijack header, severity chip and affected area',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LifelineScreen(alert: _extremeAlert, onAcknowledge: () {}),
      ),
    );

    expect(find.text('CYCLONE WARNING'), findsOneWidget);
    expect(find.text('EXTREME'), findsOneWidget);
    expect(find.textContaining('SIMULATED DRILL'), findsWidgets);
    expect(find.textContaining('Mumbai coastal belt'), findsOneWidget);
    expect(find.text('Evacuation corridor — schematic'), findsOneWidget);
  });

  testWidgets('lists relief shelters with capacity + distance', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LifelineScreen(alert: _extremeAlert, onAcknowledge: () {}),
      ),
    );

    expect(find.text('Municipal Cyclone Shelter A'), findsOneWidget);
    expect(find.text('Govt School Relief Camp'), findsOneWidget);
    expect(find.textContaining('800 capacity'), findsOneWidget);
    expect(find.textContaining('1,500 capacity'), findsOneWidget);
  });

  testWidgets('shelter tap opens the guidance callout', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LifelineScreen(alert: _extremeAlert, onAcknowledge: () {}),
      ),
    );

    await tester.tap(find.text('Municipal Cyclone Shelter A'));
    await tester.pumpAndSettle();
    expect(find.textContaining('marked corridor'), findsOneWidget);
  });

  testWidgets('offline SOS chips render from alert emergency numbers',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LifelineScreen(alert: _extremeAlert, onAcknowledge: () {}),
      ),
    );

    expect(find.textContaining('112'), findsWidgets);
    expect(find.textContaining('1078'), findsWidgets);
    expect(find.textContaining('tap to copy'), findsOneWidget);
  });

  testWidgets('SOS fallback appears when the alert has no numbers',
      (tester) async {
    const bare = DisasterProps(
      event: 'Flood',
      severity: 'Severe',
      headline: 'Severe flooding downtown',
      safetySteps: [],
      emergencyNumbers: [],
    );
    await tester.pumpWidget(
      MaterialApp(
        home: LifelineScreen(alert: bare, onAcknowledge: () {}),
      ),
    );
    expect(find.textContaining('108'), findsWidgets); // ambulance fallback
  });

  testWidgets('acknowledge button fires the callback', (tester) async {
    var acked = false;
    await tester.pumpWidget(
      MaterialApp(
        home: LifelineScreen(alert: _extremeAlert, onAcknowledge: () => acked = true),
      ),
    );

    expect(acked, isFalse);
    await tester.tap(find.text('I am safe — show weather feed'));
    expect(acked, isTrue);
  });

  testWidgets('safety-steps row opens the plan bottom sheet', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LifelineScreen(alert: _extremeAlert, onAcknowledge: () {}),
      ),
    );

    await tester.tap(find.text('Immediate safety steps'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Move to the nearest shelter'), findsOneWidget);
  });

  testWidgets('checklist row pushes the bundled offline checklists',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: LifelineScreen(alert: _extremeAlert, onAcknowledge: () {}),
      ),
    );

    await tester.tap(find.text('Disaster checklists (offline)'));
    await tester.pumpAndSettle();

    // NdmaChecklistScreen: tabs for all four hazards from the bundled asset.
    expect(find.text('Cyclone'), findsOneWidget);
    expect(find.text('Flood'), findsOneWidget);
    expect(find.text('Heat Wave'), findsOneWidget);
    expect(find.text('Lightning'), findsOneWidget);
    expect(find.textContaining('BEFORE the event'), findsOneWidget);
  });
}
