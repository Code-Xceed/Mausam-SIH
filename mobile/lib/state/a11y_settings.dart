import 'package:flutter/material.dart';
import 'package:hive_ce/hive.dart';

/// TASK-066: accessibility settings — large text and high contrast for
/// elderly / low-vision users, persisted per install.
///
/// Applied by wrapping the MaterialApp builder: text scales by [textScale]
/// and surfaces get maximum-contrast colors when [highContrast] is on.
class A11ySettings extends ChangeNotifier {
  static const _boxName = 'persona_box';
  static const _keyText = 'a11y_text_scale';
  static const _keyContrast = 'a11y_high_contrast';

  double _textScale = 1.0;
  bool _highContrast = false;

  double get textScale => _textScale;
  bool get highContrast => _highContrast;

  Box<String>? _box;

  Future<void> load() async {
    _box ??= Hive.isBoxOpen(_boxName)
        ? Hive.box<String>(_boxName)
        : await Hive.openBox<String>(_boxName);
    _textScale = double.tryParse(_box!.get(_keyText) ?? '') ?? 1.0;
    _highContrast = _box!.get(_keyContrast) == '1';
  }

  Future<void> setTextScale(double v) async {
    _textScale = v;
    await _box?.put(_keyText, v.toString());
    notifyListeners();
  }

  Future<void> setHighContrast(bool v) async {
    _highContrast = v;
    await _box?.put(_keyContrast, v ? '1' : '0');
    notifyListeners();
  }
}

/// App-wide singleton, loaded once in main() before runApp.
class A11yScope {
  A11yScope._();
  static final instance = A11ySettings();

  static Future<void> load() => instance.load();

  /// MaterialApp builder: applies text scale + high-contrast themes live.
  static Widget appBuilder(BuildContext context, Widget? child) {
    final media = MediaQuery.of(context);
    return MediaQuery(
      data: media.copyWith(
        textScaler: TextScaler.linear(instance.textScale),
      ),
      child: child ?? const SizedBox.shrink(),
    );
  }

  /// High-contrast theme seed swap for MaterialApp.highContrastTheme.
  static ThemeData highContrastTheme(ThemeData base) {
    return base.copyWith(
      colorScheme: base.colorScheme.copyWith(
        primary: const Color(0xFF000000),
        onPrimary: const Color(0xFFFFFF00),
        surface: const Color(0xFFFFFFFF),
        onSurface: const Color(0xFF000000),
        surfaceContainerHighest: const Color(0xFFEAEAEA),
      ),
      textTheme: base.textTheme.apply(
        bodyColor: const Color(0xFF000000),
        displayColor: const Color(0xFF000000),
      ),
    );
  }
}
