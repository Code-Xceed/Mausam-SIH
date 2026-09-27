import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:hive_ce_flutter/hive_flutter.dart';

/// Hive bootstrap (TASK-027). All boxes open here so cold-boot reads are
/// synchronous thereafter. Favorites/telemetry boxes are AES-encrypted; the
/// key lives in flutter_secure_storage (Android Keystore-backed), generated
/// once per install.
///
/// Boxes:
///   favorites_box      — local-first favorite locations (encrypted)
///   cached_schema_box  — last-good SDUI payload + ETag (repo uses directly)
///   persona_box        — onboarding persona tags + last location
///   telemetry_box      — offline telemetry queue (encrypted, Phase 5)
///   lifeline_box       — TASK-052 staged demo-drill payload (auto-expiring)
class HiveManager {
  static const _secure = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
  static const _keyName = 'hive_encryption_key_v1';

  static bool _ready = false;

  static Future<void> init() async {
    if (_ready) return;

    final key = await _getOrCreateKey();
    await Hive.initFlutter();

    await Hive.openBox<String>('persona_box');
    await Hive.openBox<String>('cached_schema_box');
    await Hive.openBox<String>(
      'favorites_box',
      encryptionCipher: HiveAesCipher(key),
    );
    await Hive.openBox<String>(
      'telemetry_box',
      encryptionCipher: HiveAesCipher(key),
    );

    _ready = true;
  }

  static Future<List<int>> _getOrCreateKey() async {
    String? stored;
    try {
      stored = await _secure.read(key: _keyName);
    } catch (_) {
      // Secure storage unavailable (e.g. some emulators) — degrade to
      // ephemeral key: encryption still protects at rest per session.
    }
    if (stored != null && stored.isNotEmpty) {
      return base64Decode(stored);
    }
    final key = Hive.generateSecureKey();
    try {
      await _secure.write(key: _keyName, value: base64Encode(key));
    } catch (_) {}
    return key;
  }

  /// DPDP "Clear My Footprint" (TASK-072 groundwork): wipe everything local.
  static Future<void> purgeAll() async {
    for (final name in [
      'favorites_box',
      'cached_schema_box',
      'persona_box',
      'telemetry_box',
      'lifeline_box',
    ]) {
      if (Hive.isBoxOpen(name)) {
        await Hive.box<String>(name).clear();
      }
    }
    try {
      await _secure.delete(key: _keyName);
    } catch (_) {}
  }

  static Box<String> box(String name) => Hive.box<String>(name);
}
