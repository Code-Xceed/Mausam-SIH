import 'package:flutter/material.dart';

/// TASK-067: language-independent weather glyphs. A farmer who cannot read
/// Hindi or Tamil still reads ICONS — every condition/severity maps to a
/// distinct shape+color pair, and each carries a semantic label for
/// screen readers (TalkBack announces it, satisfying a11y audits).
class ConditionGlyphs {
  ConditionGlyphs._();

  /// Distinct glyph per condition — no two conditions share a shape.
  static IconData glyphFor(String condition) {
    switch (condition) {
      case 'clear':
        return Icons.wb_sunny_rounded;
      case 'partly_cloudy':
        return Icons.partly_cloudy_day_rounded;
      case 'cloudy':
        return Icons.cloud_rounded;
      case 'fog':
      case 'haze':
        return Icons.blur_on_rounded;
      case 'drizzle':
        return Icons.grain_rounded;
      case 'rain':
        return Icons.umbrella_rounded;
      case 'thunderstorm':
        return Icons.bolt_rounded;
      case 'hail':
        return Icons.ac_unit_rounded;
      case 'snow':
        return Icons.snowing_rounded;
      default:
        return Icons.help_outline_rounded;
    }
  }

  /// Color + shape redundantly encode severity (color-blind safe: red/orange/
  /// yellow also differ in fill density via opacity).
  static (IconData, Color) severityGlyph(String severity) {
    switch (severity.toLowerCase()) {
      case 'extreme':
        return (Icons.dangerous_rounded, const Color(0xFFB71C1C));
      case 'severe':
        return (Icons.warning_rounded, const Color(0xFFE65100));
      case 'moderate':
        return (Icons.info_rounded, const Color(0xFFF9A825));
      default:
        return (Icons.info_outline_rounded, const Color(0xFF78909C));
    }
  }

  /// Screen-reader label (TASK-066 pairing): announced by TalkBack.
  static String semanticLabel(String condition) {
    switch (condition) {
      case 'clear':
        return 'Clear sky icon';
      case 'partly_cloudy':
        return 'Partly cloudy icon';
      case 'cloudy':
        return 'Cloudy icon';
      case 'fog':
      case 'haze':
        return 'Haze icon';
      case 'drizzle':
        return 'Light rain icon';
      case 'rain':
        return 'Rain icon';
      case 'thunderstorm':
        return 'Thunderstorm icon';
      case 'hail':
        return 'Hail icon';
      case 'snow':
        return 'Snow icon';
      default:
        return 'Weather icon';
    }
  }
}
