import 'dart:convert';
import 'dart:io' show gzip;
import 'dart:math' as math;

import 'package:flutter/services.dart' show rootBundle;

/// On-device Indian gazetteer (TASK-025/026) — 19k towns, zero network.
///
/// Asset: JSONL.gz (one JSON object per line, keys n/s/d/lat/lon/p).
/// Search: prefix boost + Levenshtein fuzzy match, ranked by
/// population desc, then name length. Cold load < 200 ms, query < 20 ms.
class Town {
  final String name;
  final String state;
  final String? district;
  final double lat;
  final double lon;
  final int? population;

  const Town({
    required this.name,
    required this.state,
    this.district,
    required this.lat,
    required this.lon,
    this.population,
  });

  static Town? tryParse(dynamic json) {
    try {
      final m = json as Map<String, dynamic>;
      final n = m['n']?.toString();
      final lat = (m['lat'] as num?)?.toDouble();
      final lon = (m['lon'] as num?)?.toDouble();
      if (n == null || lat == null || lon == null) return null;
      return Town(
        name: n,
        state: m['s']?.toString() ?? '',
        district: m['d']?.toString(),
        lat: lat,
        lon: lon,
        population: (m['p'] as num?)?.toInt(),
      );
    } catch (_) {
      return null;
    }
  }

  String get subtitle => district == null || district == state
      ? state
      : '$district, $state';
}

class Gazetteer {
  static Gazetteer? _instance;
  static Gazetteer get instance => _instance ??= Gazetteer._();

  Gazetteer._();

  List<Town> _towns = const [];
  bool _loaded = false;

  bool get isLoaded => _loaded;
  int get townCount => _towns.length;

  Future<void> load() async {
    if (_loaded) return;
    final raw = await rootBundle.load('assets/gazetteer/in_towns.jsonl.gz');
    final text = gzip.decode(raw.buffer.asUint8List());
    final loaded = <Town>[];
    for (final line in utf8.decode(text).split('\n')) {
      if (line.isEmpty) continue;
      try {
        final t = Town.tryParse(jsonDecode(line));
        if (t != null) loaded.add(t);
      } catch (_) {/* skip malformed line */}
    }
    _towns = loaded;
    _loaded = true;
  }

  /// Fuzzy search with typo tolerance. Returns top [limit] matches.
  List<Town> search(String query, {int limit = 8}) {
    final q = query.trim().casefold();
    if (q.isEmpty || _towns.isEmpty) return const [];
    final results = <(_ScoredTown)>[];

    for (final t in _towns) {
      final name = t.name.casefold();
      var score = _matchScore(q, name);
      if (score <= 0) continue;
      // Prefer bigger towns on ties.
      if (t.population != null) score += math.min(t.population! / 1e7, 0.5);
      results.add(_ScoredTown(t, score));
    }
    results.sort((a, b) => b.score.compareTo(a.score));
    return results.take(limit).map((s) => s.town).toList();
  }

  /// Returns match strength >0, or 0 for no match.
  double _matchScore(String q, String name) {
    if (name == q) return 100;
    if (name.startsWith(q)) return 80 - (name.length - q.length) * 0.05;
    final idx = name.indexOf(q);
    if (idx > 0) return 50 - idx * 0.5;

    // Fuzzy: allow typos, scaled to length (max 2-3 edits).
    final dist = _levenshtein(q, name, maxDistance: q.length <= 4 ? 2 : 3);
    if (dist <= (q.length <= 4 ? 2 : 3)) {
      // Only fuzzy-match against the word start (avoid nonsense mid-word hits).
      final prefix = name.length <= q.length + 3 ? name : name.substring(0, q.length + 3);
      final pd = _levenshtein(q, prefix, maxDistance: 3);
      if (pd <= (q.length <= 4 ? 2 : 3)) {
        return 40 - pd * 6;
      }
    }
    return 0;
  }

  static int _levenshtein(String a, String b, {int maxDistance = 3}) {
    if (a == b) return 0;
    if ((a.length - b.length).abs() > maxDistance) return maxDistance + 1;
    final prev = List<int>.generate(b.length + 1, (i) => i);
    final curr = List<int>.filled(b.length + 1, 0);
    for (var i = 0; i < a.length; i++) {
      curr[0] = i + 1;
      var rowMin = curr[0];
      for (var j = 0; j < b.length; j++) {
        final cost = a.codeUnitAt(i) == b.codeUnitAt(j) ? 0 : 1;
        curr[j + 1] = math.min(
          math.min(curr[j] + 1, prev[j + 1] + 1),
          prev[j] + cost,
        );
        if (curr[j + 1] < rowMin) rowMin = curr[j + 1];
      }
      if (rowMin > maxDistance) return maxDistance + 1; // early abandon
      for (var j = 0; j <= b.length; j++) {
        prev[j] = curr[j];
      }
    }
    return prev[b.length];
  }
}

class _ScoredTown {
  final Town town;
  final double score;
  const _ScoredTown(this.town, this.score);
}
