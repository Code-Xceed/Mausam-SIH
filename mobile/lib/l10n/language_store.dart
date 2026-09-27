import 'dart:convert';

import 'package:hive_ce/hive.dart';

/// TASK-063 store: the user's chosen language, persisted per install.
/// The UI bundle comes from the backend (/v1/i18n/strings/{lang}) and is
/// cached in Hive as plain JSON for offline use — switching languages never
/// needs network after the first fetch of that language.
class LanguageStore {
  static const _boxName = 'persona_box';
  static const _langKey = 'ui_language';
  static const _bundlePrefix = 'i18n_bundle_';

  static const supported = <String, String>{
    'en': 'English',
    'hi': 'हिन्दी',
    'ta': 'தமிழ்',
    'bn': 'বাংলা',
    'te': 'తెలుగు',
    'mr': 'मराठी',
  };

  Box<String>? _box;

  Future<Box<String>> get _hive async {
    _box ??= Hive.isBoxOpen(_boxName)
        ? Hive.box<String>(_boxName)
        : await Hive.openBox<String>(_boxName);
    return _box!;
  }

  Future<String> load() async => (await _hive).get(_langKey) ?? 'en';

  Future<void> save(String code) async {
    assert(supported.containsKey(code), 'unsupported language $code');
    await (await _hive).put(_langKey, code);
  }

  /// Cached UI bundle for [code], or null (caller fetches from the backend).
  Future<Map<String, dynamic>?> loadBundle(String code) async {
    final raw = (await _hive).get('$_bundlePrefix$code');
    if (raw == null) return null;
    try {
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return null;
    }
  }

  Future<void> saveBundle(String code, Map<String, dynamic> bundle) async {
    await (await _hive).put('$_bundlePrefix$code', jsonEncode(bundle));
  }
}
