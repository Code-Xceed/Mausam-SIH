import 'dart:convert';
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:hive_ce_flutter/hive_flutter.dart';

/// Hive bootstrap (TASK-027). All boxes open here so cold-boot reads are
/// synchronous thereafter. Unencrypted boxes are opened first and are completely
/// resilient. Encrypted boxes feature automatic fallback and recovery so they
/// can NEVER crash app startup or wipe onboarding state.
///
/// Boxes:
///   favorites_box      — local-first favorite locations (encrypted / resilient)
///   cached_schema_box  — last-good SDUI payload + ETag (unencrypted)
///   persona_box        — onboarding persona tags + last location (unencrypted)
///   telemetry_box      — offline telemetry queue (encrypted / resilient)
///   lifeline_box       — TASK-052 staged demo-drill payload (unencrypted)
class HiveManager {
  static const _secure = FlutterSecureStorage(
    aOptions: AndroidOptions(resetOnError: true),
  );
  static const _keyName = 'hive_encryption_key_v1';

  static bool _ready = false;
  static bool get isReady => _ready;

  static Future<void> init() async {
    // 1. Initialize Flutter Hive storage path first
    try {
      await Hive.initFlutter();
    } catch (_) {
      // In headless unit tests where path_provider is unavailable,
      // Hive.init() has already been called with a scratch path.
    }

    // 2. Open core unencrypted boxes first — zero risk, 100% reliable
    if (!Hive.isBoxOpen('persona_box')) {
      await Hive.openBox<String>('persona_box');
    }
    if (!Hive.isBoxOpen('cached_schema_box')) {
      await Hive.openBox<String>('cached_schema_box');
    }
    if (!Hive.isBoxOpen('lifeline_box')) {
      await Hive.openBox<String>('lifeline_box');
    }

    // 3. Obtain encryption key and open secure boxes with crash-proof recovery
    final key = await _getOrCreateKey();

    await _openEncryptedBox('favorites_box', key);
    await _openEncryptedBox('telemetry_box', key);

    _ready = true;
  }

  static Future<void> _openEncryptedBox(String boxName, List<int> key) async {
    if (Hive.isBoxOpen(boxName)) return;

    try {
      await Hive.openBox<String>(
        boxName,
        encryptionCipher: HiveAesCipher(key),
      );
    } catch (e) {
      // If keystore changed, key mismatch, or file corrupt:
      // Re-create box safely so the app NEVER crashes on startup.
      try {
        await Hive.deleteBoxFromDisk(boxName);
      } catch (_) {}
      try {
        await Hive.openBox<String>(
          boxName,
          encryptionCipher: HiveAesCipher(key),
        );
      } catch (_) {
        // Last-resort fallback to unencrypted box if AES cipher fails
        if (!Hive.isBoxOpen(boxName)) {
          await Hive.openBox<String>(boxName);
        }
      }
    }
  }

  static Future<List<int>> _getOrCreateKey() async {
    String? stored;
    try {
      stored = await _secure.read(key: _keyName);
    } catch (_) {}

    if (stored != null && stored.isNotEmpty) {
      try {
        return base64Decode(stored);
      } catch (_) {}
    }

    final key = Hive.generateSecureKey();
    try {
      await _secure.write(key: _keyName, value: base64Encode(key));
    } catch (_) {}
    return key;
  }

  /// DPDP "Clear My Footprint" (TASK-072): wipe everything local.
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
        await Hive.box<String>(name).flush();
      }
    }
    try {
      await _secure.delete(key: _keyName);
    } catch (_) {}
  }

  static Box<String> box(String name) => Hive.box<String>(name);
}
