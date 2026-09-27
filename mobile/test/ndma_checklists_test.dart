import 'package:flutter_test/flutter_test.dart';
import 'package:mausam_nextgen/safety/ndma_checklists.dart';

/// TASK-053: the bundled NDMA checklists must parse and stay available fully
/// offline — `flutter test` serves pubspec-declared assets, so these prove
/// the real asset in the binary parses into the expected shape.
///
///   cd mobile && flutter test test/ndma_checklists_test.dart

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('bundled asset parses: 4 hazards, all phases populated', () async {
    final data = await NdmaChecklists.load();

    expect(
      data.hazards.map((h) => h.key).toSet(),
      containsAll(<String>{'cyclone', 'flood', 'heatwave', 'lightning'}),
    );
    for (final h in data.hazards) {
      expect(h.title, isNotEmpty);
      expect(h.before, isNotEmpty, reason: '${h.key}.before must have steps');
      expect(h.during, isNotEmpty, reason: '${h.key}.during must have steps');
      expect(h.after, isNotEmpty, reason: '${h.key}.after must have steps');
    }
    // Every step is meaningful text (no empty/broken entries).
    for (final h in data.hazards) {
      for (final s in [...h.before, ...h.during, ...h.after]) {
        expect(s.trim().length, greaterThan(10), reason: 'suspicious step: "$s"');
      }
    }
  });

  test('lifeline-relevant hazards carry life-saving specifics', () async {
    final data = await NdmaChecklists.load();

    final cyclone = data.hazards.firstWhere((h) => h.key == 'cyclone');
    expect(
      cyclone.during.join(' '),
      containsIgnoringCase('eye'),
      reason: 'cyclone during-steps must warn about the eye-of-the-storm lull',
    );

    final flood = data.hazards.firstWhere((h) => h.key == 'flood');
    expect(
      flood.during.join(' '),
      containsIgnoringCase('flowing water'),
    );

    final heat = data.hazards.firstWhere((h) => h.key == 'heatwave');
    expect(
      heat.during.join(' '),
      containsIgnoringCase('heat stroke'),
    );

    final lightning = data.hazards.firstWhere((h) => h.key == 'lightning');
    expect(
      lightning.after.join(' '),
      containsIgnoringCase('no electric charge'),
    );
  });

  test('emergency numbers include the national lifelines', () async {
    final data = await NdmaChecklists.load();
    final numbers = data.emergencyNumbers.map((c) => c.number).toSet();
    expect(numbers, containsAll(<String>{'112', '1078', '108'}));
  });

  test('load() is cached and idempotent', () async {
    final a = await NdmaChecklists.load();
    final b = await NdmaChecklists.load();
    expect(identical(a, b), isTrue, reason: 'second load must hit the cache');
  });
}

class _ContainsIgnoringCase extends Matcher {
  final String _needle;
  const _ContainsIgnoringCase(this._needle);

  @override
  bool matches(Object? item, Map<dynamic, dynamic> matchState) =>
      item is String && item.toLowerCase().contains(_needle.toLowerCase());

  @override
  Description describe(Description description) => description
      .add('contains (case-insensitive) ')
      .addDescriptionOf(_needle);
}

Matcher containsIgnoringCase(String needle) => _ContainsIgnoringCase(needle);
