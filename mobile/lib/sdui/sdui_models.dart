import 'package:flutter/foundation.dart';

/// SDUI v1 client models (mirrors contracts/sdui_v1.schema.json).
///
/// Parsing is deliberately defensive: every accessor has a fallback so a
/// malformed server payload can never throw during build — the card either
/// renders with best-effort data or is skipped entirely (TASK-018).

@immutable
class SduiPayload {
  final String schemaVersion;
  final String displayName;
  final String? district;
  final String? state;
  final List<String> activePersonas;
  final List<String> sourcesUsed;
  final bool stale;
  final List<SduiWidget> widgets;

  const SduiPayload({
    required this.schemaVersion,
    required this.displayName,
    this.district,
    this.state,
    required this.activePersonas,
    required this.sourcesUsed,
    required this.stale,
    required this.widgets,
  });

  static SduiPayload? tryParse(Map<String, dynamic> json) {
    try {
      final loc = (json['location'] as Map<String, dynamic>?) ?? const {};
      final personas = (json['personas'] as Map<String, dynamic>?) ?? const {};
      final rawWidgets = (json['widgets'] as List?) ?? const [];
      final widgets = <SduiWidget>[];
      for (final w in rawWidgets) {
        final parsed = SduiWidget.tryParse(w as Map<String, dynamic>);
        if (parsed != null) widgets.add(parsed); // unknown/broken → skipped
      }
      return SduiPayload(
        schemaVersion: json['schema_version']?.toString() ?? 'v1',
        displayName: loc['display_name']?.toString() ?? 'Unknown',
        district: loc['district']?.toString(),
        state: loc['state']?.toString(),
        activePersonas: ((personas['active'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
        sourcesUsed: ((json['sources_used'] as List?) ?? const [])
            .map((e) => e.toString())
            .toList(),
        stale: json['stale'] == true,
        widgets: widgets,
      );
    } catch (_) {
      return null; // contract violation → caller renders fallback layout
    }
  }
}

@immutable
class SduiWidget {
  final String id;
  final String type;
  final Map<String, dynamic> props;
  final int priority;

  const SduiWidget({
    required this.id,
    required this.type,
    required this.props,
    required this.priority,
  });

  static SduiWidget? tryParse(Map<String, dynamic> json) {
    final type = json['type']?.toString();
    if (type == null || type.isEmpty) return null;
    return SduiWidget(
      id: json['id']?.toString() ?? type,
      type: type,
      props: (json['props'] as Map<String, dynamic>?) ?? const {},
      priority: (json['priority'] as num?)?.toInt() ?? 0,
    );
  }
}

// --------------------------------------------------------------------------- //
// Typed prop views (all nullable-safe; builders never throw on bad data)
// --------------------------------------------------------------------------- //

@immutable
class CurrentProps {
  final double temperatureC;
  final double? feelsLikeC;
  final String condition;
  final String conditionText;
  final double humidityPct;
  final double windKmph;
  final double? uvIndex;
  final String? uvAdvice;
  final String observedAt;

  const CurrentProps({
    required this.temperatureC,
    this.feelsLikeC,
    required this.condition,
    required this.conditionText,
    required this.humidityPct,
    required this.windKmph,
    this.uvIndex,
    this.uvAdvice,
    required this.observedAt,
  });

  static CurrentProps? tryParse(Map<String, dynamic> p) {
    final t = (p['temperature_c'] as num?)?.toDouble();
    if (t == null) return null;
    return CurrentProps(
      temperatureC: t,
      feelsLikeC: (p['feels_like_c'] as num?)?.toDouble(),
      condition: p['condition']?.toString() ?? 'partly_cloudy',
      conditionText: p['condition_text']?.toString() ?? '',
      humidityPct: (p['humidity_pct'] as num?)?.toDouble() ?? 0,
      windKmph: (p['wind_kmph'] as num?)?.toDouble() ?? 0,
      uvIndex: (p['uv_index'] as num?)?.toDouble(),
      uvAdvice: p['uv_advice']?.toString(),
      observedAt: p['observed_at']?.toString() ?? '',
    );
  }
}

@immutable
class AqiProps {
  final int aqi;
  final String category;
  final String? dominatingPollutant;
  final double? pm25;
  final double? pm10;
  final String advice;

  const AqiProps({
    required this.aqi,
    required this.category,
    this.dominatingPollutant,
    this.pm25,
    this.pm10,
    required this.advice,
  });

  static AqiProps? tryParse(Map<String, dynamic> p) {
    final aqi = (p['aqi'] as num?)?.toInt();
    if (aqi == null) return null;
    return AqiProps(
      aqi: aqi,
      category: p['category']?.toString() ?? 'Unknown',
      dominatingPollutant: p['dominating_pollutant']?.toString(),
      pm25: (p['pm2_5_ugm3'] as num?)?.toDouble(),
      pm10: (p['pm10_ugm3'] as num?)?.toDouble(),
      advice: p['advice']?.toString() ?? '',
    );
  }
}

@immutable
class MarineProps {
  final double? waveHeightM;
  final double? swellPeriodS;
  final double? sstC;
  final String? tideState;
  final String? nextHighTide;
  final String? nextLowTide;
  final String? beachFlag;
  final String beachNote;
  final bool surfOk;
  final List<TidePoint> tideCurve;

  const MarineProps({
    this.waveHeightM,
    this.swellPeriodS,
    this.sstC,
    this.tideState,
    this.nextHighTide,
    this.nextLowTide,
    this.beachFlag,
    required this.beachNote,
    required this.surfOk,
    required this.tideCurve,
  });

  static MarineProps? tryParse(Map<String, dynamic> p) {
    final wave = (p['wave_height_m'] as num?)?.toDouble();
    if (wave == null && p['tide_state'] == null) return null;
    final curve = ((p['tide_curve'] as List?) ?? const [])
        .map((e) => TidePoint.tryParse(e as Map<String, dynamic>))
        .whereType<TidePoint>()
        .toList();
    return MarineProps(
      waveHeightM: wave,
      swellPeriodS: (p['swell_period_s'] as num?)?.toDouble(),
      sstC: (p['sst_c'] as num?)?.toDouble(),
      tideState: p['tide_state']?.toString(),
      nextHighTide: p['next_high_tide']?.toString(),
      nextLowTide: p['next_low_tide']?.toString(),
      beachFlag: p['beach_flag']?.toString(),
      beachNote: p['beach_note']?.toString() ?? '',
      surfOk: p['surf_ok'] == true,
      tideCurve: curve,
    );
  }
}

@immutable
class TidePoint {
  final DateTime time;
  final double heightM;

  const TidePoint({required this.time, required this.heightM});

  static TidePoint? tryParse(Map<String, dynamic> p) {
    final t = DateTime.tryParse(p['time']?.toString() ?? '');
    final h = (p['height_m'] as num?)?.toDouble();
    if (t == null || h == null) return null;
    return TidePoint(time: t, heightM: h);
  }
}

@immutable
class CommuteProps {
  final String alertLevel;
  final String message;
  final int rainStartHour;
  final int estimatedDelayMin;

  const CommuteProps({
    required this.alertLevel,
    required this.message,
    required this.rainStartHour,
    required this.estimatedDelayMin,
  });

  static CommuteProps? tryParse(Map<String, dynamic> p) {
    final msg = p['message']?.toString();
    if (msg == null || msg.isEmpty) return null;
    return CommuteProps(
      alertLevel: p['alert_level']?.toString() ?? 'rain',
      message: msg,
      rainStartHour: (p['rain_start_hour'] as num?)?.toInt() ?? 0,
      estimatedDelayMin: (p['estimated_delay_min'] as num?)?.toInt() ?? 0,
    );
  }
}

@immutable
class VisibilityProps {
  final int visibilityM;
  final double fogIndex;
  final String note;

  const VisibilityProps({
    required this.visibilityM,
    required this.fogIndex,
    required this.note,
  });

  static VisibilityProps? tryParse(Map<String, dynamic> p) {
    final v = (p['visibility_m'] as num?)?.toInt();
    if (v == null) return null;
    return VisibilityProps(
      visibilityM: v,
      fogIndex: (p['fog_index'] as num?)?.toDouble() ?? 0,
      note: p['note']?.toString() ?? '',
    );
  }
}

@immutable
class AgroProps {
  final String blockName;
  final String? amfuName;
  final List<String> advisories;
  final double? soilMoisturePct;
  final bool frostRisk;
  final String? issuedOn;

  const AgroProps({
    required this.blockName,
    this.amfuName,
    required this.advisories,
    this.soilMoisturePct,
    required this.frostRisk,
    this.issuedOn,
  });

  static AgroProps? tryParse(Map<String, dynamic> p) {
    final block = p['block_name']?.toString();
    if (block == null) return null;
    return AgroProps(
      blockName: block,
      amfuName: p['amfu_name']?.toString(),
      advisories: ((p['advisories'] as List?) ?? const [])
          .map((e) => e.toString())
          .toList(),
      soilMoisturePct: (p['soil_moisture_pct'] as num?)?.toDouble(),
      frostRisk: p['frost_risk'] == true,
      issuedOn: p['issued_on']?.toString(),
    );
  }
}

@immutable
class DisasterProps {
  final String event;
  final String severity;
  final String headline;
  final String? instruction;
  final String? areaDesc;
  final List<String> safetySteps;
  final List<EmergencyContact> emergencyNumbers;

  const DisasterProps({
    required this.event,
    required this.severity,
    required this.headline,
    this.instruction,
    this.areaDesc,
    required this.safetySteps,
    required this.emergencyNumbers,
  });

  static DisasterProps? tryParse(Map<String, dynamic> p) {
    final headline = p['headline']?.toString();
    if (headline == null) return null;
    return DisasterProps(
      event: p['event']?.toString() ?? 'Weather Alert',
      severity: p['severity']?.toString() ?? 'Unknown',
      headline: headline,
      instruction: p['instruction']?.toString(),
      areaDesc: p['area_desc']?.toString(),
      safetySteps: ((p['safety_steps'] as List?) ?? const [])
          .map((e) => e.toString())
          .toList(),
      emergencyNumbers: ((p['emergency_numbers'] as List?) ?? const [])
          .map((e) => EmergencyContact.tryParse(e as Map<String, dynamic>))
          .whereType<EmergencyContact>()
          .toList(),
    );
  }
}

@immutable
class EmergencyContact {
  final String label;
  final String number;

  const EmergencyContact({required this.label, required this.number});

  static EmergencyContact? tryParse(Map<String, dynamic> p) {
    final n = p['number']?.toString();
    if (n == null) return null;
    return EmergencyContact(label: p['label']?.toString() ?? '', number: n);
  }
}

@immutable
class PackingProps {
  final List<String> packing;
  final List<PackingDay> days;

  const PackingProps({required this.packing, required this.days});

  static PackingProps? tryParse(Map<String, dynamic> p) {
    final days = ((p['days'] as List?) ?? const [])
        .map((e) => PackingDay.tryParse(e as Map<String, dynamic>))
        .whereType<PackingDay>()
        .toList();
    if (days.isEmpty) return null;
    return PackingProps(
      packing: ((p['packing'] as List?) ?? const [])
          .map((e) => e.toString())
          .toList(),
      days: days,
    );
  }
}

@immutable
class PackingDay {
  final String date;
  final double tempMaxC;
  final double tempMinC;
  final String condition;
  final int rainPct;

  const PackingDay({
    required this.date,
    required this.tempMaxC,
    required this.tempMinC,
    required this.condition,
    required this.rainPct,
  });

  static PackingDay? tryParse(Map<String, dynamic> p) {
    final d = p['date']?.toString();
    final max = (p['temp_max_c'] as num?)?.toDouble();
    if (d == null || max == null) return null;
    return PackingDay(
      date: d,
      tempMaxC: max,
      tempMinC: (p['temp_min_c'] as num?)?.toDouble() ?? max,
      condition: p['condition']?.toString() ?? 'cloudy',
      rainPct: (p['rain_pct'] as num?)?.toInt() ?? 0,
    );
  }
}

@immutable
class EventCalendarProps {
  final List<EventDay> days;

  const EventCalendarProps({required this.days});

  static EventCalendarProps? tryParse(Map<String, dynamic> p) {
    final days = ((p['days'] as List?) ?? const [])
        .map((e) => EventDay.tryParse(e as Map<String, dynamic>))
        .whereType<EventDay>()
        .toList();
    if (days.isEmpty) return null;
    return EventCalendarProps(days: days);
  }
}

@immutable
class EventDay {
  final String date;
  final int score;
  final String suitability;
  final String condition;
  final int rainPct;

  const EventDay({
    required this.date,
    required this.score,
    required this.suitability,
    required this.condition,
    required this.rainPct,
  });

  static EventDay? tryParse(Map<String, dynamic> p) {
    final d = p['date']?.toString();
    final s = (p['score'] as num?)?.toInt();
    if (d == null || s == null) return null;
    return EventDay(
      date: d,
      score: s,
      suitability: p['suitability']?.toString() ?? 'fair',
      condition: p['condition']?.toString() ?? 'cloudy',
      rainPct: (p['rain_pct'] as num?)?.toInt() ?? 0,
    );
  }
}

@immutable
class RunningProps {
  final List<RunWindow> windows;

  const RunningProps({required this.windows});

  static RunningProps? tryParse(Map<String, dynamic> p) {
    final windows = ((p['windows'] as List?) ?? const [])
        .map((e) => RunWindow.tryParse(e as Map<String, dynamic>))
        .whereType<RunWindow>()
        .toList();
    if (windows.isEmpty) return null;
    return RunningProps(windows: windows);
  }
}

@immutable
class CitySummary {
  final String name;
  final double lat;
  final double lon;
  final double tempMaxC;
  final double tempMinC;
  final String condition;
  final int rainPct;

  const CitySummary({
    required this.name,
    required this.lat,
    required this.lon,
    required this.tempMaxC,
    required this.tempMinC,
    required this.condition,
    required this.rainPct,
  });

  static CitySummary? tryParse(Map<String, dynamic> p) {
    final n = p['name']?.toString();
    final lat = (p['lat'] as num?)?.toDouble();
    final lon = (p['lon'] as num?)?.toDouble();
    if (n == null || lat == null || lon == null) return null;
    return CitySummary(
      name: n,
      lat: lat,
      lon: lon,
      tempMaxC: (p['temp_max_c'] as num?)?.toDouble() ?? 0,
      tempMinC: (p['temp_min_c'] as num?)?.toDouble() ?? 0,
      condition: p['condition']?.toString() ?? 'cloudy',
      rainPct: (p['rain_pct'] as num?)?.toInt() ?? 0,
    );
  }
}

@immutable
class RunWindow {
  final int startHour;
  final int endHour;
  final double? avgTempC;
  final String rating;

  const RunWindow({
    required this.startHour,
    required this.endHour,
    this.avgTempC,
    required this.rating,
  });

  static RunWindow? tryParse(Map<String, dynamic> p) {
    final s = (p['start_hour'] as num?)?.toInt();
    final e = (p['end_hour'] as num?)?.toInt();
    if (s == null || e == null) return null;
    return RunWindow(
      startHour: s,
      endHour: e,
      avgTempC: (p['avg_temp_c'] as num?)?.toDouble(),
      rating: p['rating']?.toString() ?? 'good',
    );
  }
}
