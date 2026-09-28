import 'dart:async';
import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:hive_ce/hive.dart';
import 'package:http/http.dart' as http;

import '../state/persona_store.dart';
import 'sdui_models.dart';

/// SDUI repository: fetch → 304 revalidation → Hive persistence → bundled
/// fallback. The homepage renders from local storage first (offline-first),
/// then refreshes. ETag lets the server answer "not modified" cheaply.
class SduiRepository {
  SduiRepository({http.Client? client, String? baseUrl})
      : _client = client ?? http.Client(),
        baseUrl = baseUrl ??
            const String.fromEnvironment(
              'BACKEND_URL',
              defaultValue: 'https://mausam-nextgen.onrender.com',
            );

  final http.Client _client;
  final String baseUrl;

  Future<String> get activeBaseUrl async {
    final custom = await PersonaStore().loadServerUrl();
    if (custom != null && custom.isNotEmpty) return custom;
    return baseUrl;
  }

  static const _boxName = 'cached_schema_box';
  static const _etagKey = 'sdui_home_etag';
  static const _bodyKey = 'sdui_home_body';

  Box<String>? _box;

  Future<Box<String>> get _cache async {
    _box ??= await Hive.openBox<String>(_boxName);
    return _box!;
  }

  /// Returns the freshest available payload, or null only if nothing was
  /// ever cached AND the bundled fallback is missing (should not happen).
  ///
  /// [cities] feeds the multi-city travel carousel (TASK-034) as
  /// 'lat:lon,lat:lon' pairs — the server summarizes each in parallel.
  Future<SduiPayload?> loadHome({
    required double lat,
    required double lon,
    required List<String> personas,
    List<(double, double)> cities = const [],
  }) async {
    final box = await _cache;
    final cachedBody = box.get(_bodyKey);
    final etag = box.get(_etagKey);

    // 1. Instant render from cache.
    SduiPayload? cached;
    if (cachedBody != null) {
      cached = _decode(cachedBody);
    }

    // 2. Background revalidation (best effort).
    try {
      final citiesParam = cities
          .take(5)
          .map((c) => '${c.$1.toStringAsFixed(4)}:${c.$2.toStringAsFixed(4)}')
          .join(',');
      final effectiveUrl = await activeBaseUrl;
      final uri = Uri.parse(
        '$effectiveUrl/v1/sdui/home?lat=$lat&lon=$lon'
        '&personas=${personas.join(",")}'
        '${citiesParam.isEmpty ? '' : '&cities=$citiesParam'}',
      );
      final headers = <String, String>{
        'Accept-Encoding': 'br',
        if (etag != null) 'If-None-Match': etag,
      };
      final res = await _client.get(uri, headers: headers).timeout(
            // 12 s: serverless hosts (Render free tier) sleep after ~15 min
            // idle and can take ~30 s to wake; the cached payload renders
            // instantly meanwhile, so this only delays revalidation.
            const Duration(seconds: 12),
          );

      if (res.statusCode == 304 && cached != null) {
        return cached; // server confirms freshness
      }
      if (res.statusCode == 200) {
        // http package transparently decompresses Brotli when the platform
        // supports it; otherwise the server sent identity (no br support).
        final body = utf8.decode(res.bodyBytes);
        final payload = _decode(body);
        if (payload != null) {
          await box.put(_bodyKey, body);
          final newEtag = res.headers['etag'];
          if (newEtag != null) await box.put(_etagKey, newEtag);
          return payload;
        }
      }
    } catch (_) {
      // Network dead — fall through to cached/fallback.
    }

    // 3. Cache hit wins over bundled fallback (fresher), provided it is not an old dummy
    if (cached != null) {
      final isDummy = cached.widgets.length <= 2 &&
          cached.widgets.any((w) =>
              w.type == 'current_conditions' &&
              w.props['temperature_c'] == 0 &&
              w.props['wind_kmph'] == 0);
      if (!isDummy) return cached;
    }

    // 4. Bundled fallback layout (TASK-019) — never a blank screen.
    return _bundledFallback();
  }

  SduiPayload? _decode(String body) {
    try {
      return SduiPayload.tryParse(jsonDecode(body) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  Future<SduiPayload?> _bundledFallback() async {
    try {
      final raw = await rootBundle.loadString('assets/fallback/home_fallback.json');
      return _decode(raw);
    } catch (_) {
      return null;
    }
  }

  /// Test/dev hook: clears cached schema.
  Future<void> clearCache() async {
    final box = await _cache;
    await box.clear();
  }
}
