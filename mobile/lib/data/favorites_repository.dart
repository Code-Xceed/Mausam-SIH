import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:hive_ce/hive.dart';
import 'package:http/http.dart' as http;

/// A saved (favorite) location — stored locally, mirrored to the cloud.
class FavoriteLocation {
  final String name;
  final String state;
  final double lat;
  final double lon;
  final DateTime addedAt;

  const FavoriteLocation({
    required this.name,
    required this.state,
    required this.lat,
    required this.lon,
    required this.addedAt,
  });

  Map<String, dynamic> toJson() => {
        'name': name,
        'state': state,
        'lat': lat,
        'lon': lon,
        'added_at': addedAt.toIso8601String(),
      };

  static FavoriteLocation? tryParse(Map<String, dynamic> j) {
    final n = j['name']?.toString();
    final lat = (j['lat'] as num?)?.toDouble();
    final lon = (j['lon'] as num?)?.toDouble();
    if (n == null || lat == null || lon == null) return null;
    return FavoriteLocation(
      name: n,
      state: j['state']?.toString() ?? '',
      lat: lat,
      lon: lon,
      addedAt: DateTime.tryParse(j['added_at']?.toString() ?? '') ?? DateTime.now(),
    );
  }
}

/// Local-first dual-write favorites (TASK-028).
///
/// WRITE PATH: tap star → Hive (synchronous, instant) → background HTTP push.
/// READ PATH: boot → Hive. The server is a restore mirror, never a
/// dependency — this is the fix for the legacy "favorites wiped" bug.
class FavoritesRepository {
  FavoritesRepository({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        baseUrl = baseUrl ??
            const String.fromEnvironment(
              'BACKEND_URL',
              defaultValue: 'http://10.0.2.2:8000',
            );

  final http.Client _client;
  final String baseUrl;

  static const _boxName = 'favorites_box';

  Box<String> get _box => Hive.box<String>(_boxName);

  /// Stable anonymous device hash for the sync mirror (DPDP: not a raw id).
  String _deviceHash() {
    final raw = _box.get('device_salt') ?? '';
    if (raw.isEmpty) {
      final salt = DateTime.now().microsecondsSinceEpoch.toString();
      _box.put('device_salt', salt);
      return sha256.convert(utf8.encode('mausam-$salt')).toString().substring(0, 32);
    }
    return sha256.convert(utf8.encode('mausam-$raw')).toString().substring(0, 32);
  }

  List<FavoriteLocation> _parseAll() {
    final raw = _box.get('favorites');
    if (raw == null || raw.isEmpty) return [];
    try {
      final list = (jsonDecode(raw) as List)
          .map((e) => FavoriteLocation.tryParse(e as Map<String, dynamic>))
          .whereType<FavoriteLocation>()
          .toList();
      return list;
    } catch (_) {
      return [];
    }
  }

  /// Synchronous local read — instant cold-boot render.
  List<FavoriteLocation> allSync() => _parseAll();

  /// THE dual write: commit locally first (never fails on network), then
  /// fire-and-forget the cloud mirror.
  Future<void> add(FavoriteLocation fav) async {
    final current = _parseAll();
    // Dedupe by (name, state).
    current.removeWhere(
      (f) => f.name == fav.name && f.state == fav.state,
    );
    current.insert(0, fav);
    await _box.put('favorites', jsonEncode(current.map((f) => f.toJson()).toList()));
    _syncInBackground();
  }

  Future<void> remove(String name, String state) async {
    final current = _parseAll()
      ..removeWhere((f) => f.name == name && f.state == state);
    await _box.put('favorites', jsonEncode(current.map((f) => f.toJson()).toList()));
    _syncInBackground();
  }

  bool isFavorite(String name, String state) =>
      _parseAll().any((f) => f.name == name && f.state == state);

  /// Background cloud mirror — best effort, silently retried next write.
  void _syncInBackground() {
    final favorites = _parseAll();
    final hash = _deviceHash();
    http
        .post(
          Uri.parse('$baseUrl/v1/favorites/sync'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'device_id_hash': hash,
            'favorites': favorites.map((f) => f.toJson()).toList(),
          }),
        )
        .timeout(const Duration(seconds: 5))
        .catchError((_) {/* local copy is the source of truth; ignore */});
  }

  /// One-tap restore: pull server mirror (new device / reinstall).
  Future<void> restoreFromCloud() async {
    try {
      final res = await _client
          .get(Uri.parse('$baseUrl/v1/favorites/sync/${_deviceHash()}'))
          .timeout(const Duration(seconds: 5));
      if (res.statusCode != 200) return;
      final list = ((jsonDecode(res.body) as Map<String, dynamic>)['favorites']
              as List?) ??
          const [];
      final remote = list
          .map((e) => FavoriteLocation.tryParse(e as Map<String, dynamic>))
          .whereType<FavoriteLocation>()
          .toList();
      if (remote.isEmpty) return;
      // Merge: remote entries not already local (by name+state).
      final local = _parseAll();
      final keys = local.map((f) => '${f.name}|${f.state}').toSet();
      for (final r in remote) {
        if (keys.add('${r.name}|${r.state}')) local.add(r);
      }
      await _box.put('favorites', jsonEncode(local.map((f) => f.toJson()).toList()));
    } catch (_) {/* offline — local stays authoritative */}
  }

  /// DPDP purge (TASK-072 hook).
  Future<void> purgeAll() async {
    await _box.delete('favorites');
    try {
      await _client
          .delete(Uri.parse('$baseUrl/v1/favorites/sync/${_deviceHash()}'))
          .timeout(const Duration(seconds: 3));
    } catch (_) {}
  }
}
