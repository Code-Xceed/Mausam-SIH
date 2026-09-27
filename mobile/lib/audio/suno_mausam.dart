import 'dart:convert';

import 'package:flutter_tts/flutter_tts.dart';
import 'package:hive_ce/hive.dart';

/// "Suno Mausam" (TASK-064/065): regional audio TTS for advisories.
///
/// Offline story (TASK-065): Android/iOS system TTS engines synthesize
/// ON-DEVICE — no network needed once the language voice pack is installed.
/// We additionally cache the last bulletin TEXT per language in Hive, so a
/// cold airplane-mode boot can re-speak the last advisory immediately.
class SunoMausam {
  SunoMausam._();
  static final instance = SunoMausam._();

  final FlutterTts _tts = FlutterTts();
  bool _initialized = false;

  static const _boxName = 'persona_box';
  static const _cachePrefix = 'tts_bulletin_';

  static const _localeFor = <String, String>{
    'en': 'en-IN',
    'hi': 'hi-IN',
    'ta': 'ta-IN',
    'bn': 'bn-IN',
    'te': 'te-IN',
    'mr': 'mr-IN',
  };

  Future<void> _ensure(String lang) async {
    if (_initialized) return;
    await _tts.setSpeechRate(0.5); // slower = clearer for advisories
    await _tts.setVolume(1.0);
    await _tts.setPitch(1.0);
    _initialized = true;
    // Best-effort locale set; unsupported engines fall back silently.
    try {
      await _tts.setLanguage(_localeFor[lang] ?? 'en-IN');
    } catch (_) {}
  }

  /// Speak the latest advisory in [lang]. Re-uses the cached text when
  /// [text] is null (offline replay of the last bulletin).
  Future<bool> speak(String text, {String lang = 'en'}) async {
    await _ensure(lang);
    try {
      await _tts.setLanguage(_localeFor[lang] ?? 'en-IN');
      await _cacheBulletin(lang, text);
      await _tts.speak(text);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// TASK-065: re-speak the last cached bulletin without any network.
  Future<bool> speakLastBulletin({String lang = 'en'}) async {
    final cached = await _lastBulletin(lang);
    if (cached == null) return false;
    return speak(cached, lang: lang);
  }

  Future<void> stop() async {
    try {
      await _tts.stop();
    } catch (_) {}
  }

  Future<Box<String>> get _box async {
    return Hive.isBoxOpen(_boxName)
        ? Hive.box<String>(_boxName)
        : Hive.openBox<String>(_boxName);
  }

  Future<void> _cacheBulletin(String lang, String text) async {
    final payload = jsonEncode({
      'text': text,
      'at': DateTime.now().toIso8601String(),
    });
    await (await _box).put('$_cachePrefix$lang', payload);
  }

  Future<String?> _lastBulletin(String lang) async {
    final raw = (await _box).get('$_cachePrefix$lang');
    if (raw == null) return null;
    try {
      return (jsonDecode(raw) as Map<String, dynamic>)['text']?.toString();
    } catch (_) {
      return null;
    }
  }
}
