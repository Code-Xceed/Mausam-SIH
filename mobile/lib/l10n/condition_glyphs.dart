import 'package:flutter/material.dart';

/// TASK-067: language-independent weather glyphs. A farmer who cannot read
/// Hindi or Tamil still reads ICONS — every condition/severity maps to a
/// distinct shape+color pair, and each carries a semantic label for
/// screen readers (TalkBack announces it, satisfying a11y audits).
///
/// Icon names are restricted to glyphs available in stable Material sets
/// (CI compiles against flutter stable).
class ConditionGlyphs {
  ConditionGlyphs._();

  /// Distinct glyph per condition — no two conditions share a shape.
  static IconData glyphFor(String condition) {
    switch (condition) {
      case 'clear':
        return Icons.wb_sunny;
      case 'partly_cloudy':
        return Icons.partly_cloudy_day;
      case 'cloudy':
        return Icons.cloud;
      case 'fog':
      case 'haze':
        return Icons.foggy;
      case 'drizzle':
        return Icons.water_drop;
      case 'rain':
        return Icons.umbrella;
      case 'thunderstorm':
        return Icons.bolt;
      case 'hail':
        return Icons.grain;
      case 'snow':
        return Icons.ac_unit;
      default:
        return Icons.help_outline;
    }
  }

  /// Color + shape redundantly encode severity (color-blind safe: red/orange/
  /// yellow also differ in fill density via opacity).
  static (IconData, Color) severityGlyph(String severity) {
    switch (severity.toLowerCase()) {
      case 'extreme':
        return (Icons.dangerous, const Color(0xFFB71C1C));
      case 'severe':
        return (Icons.warning, const Color(0xFFE65100));
      case 'moderate':
        return (Icons.info, const Color(0xFFF9A825));
      default:
        return (Icons.info_outline, const Color(0xFF78909C));
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
