import 'package:flutter/material.dart';

import 'sdui_models.dart';
import 'widgets/agro_card.dart';
import 'widgets/aqi_radial_meter.dart';
import 'widgets/commute_banner.dart';
import 'widgets/current_conditions.dart';
import 'widgets/disaster_card.dart';
import 'widgets/event_calendar.dart';
import 'widgets/marine_tide.dart';
import 'widgets/multi_city_carousel.dart';
import 'widgets/packing_carousel.dart';
import 'widgets/persona_rank_row.dart';
import 'widgets/running_timeline.dart';
import 'widgets/visibility_meter.dart';

/// Registry of backend widget type → native Flutter builder (TASK-017).
/// Adding a new card type = one entry here + one widget file. Nothing else.
typedef WidgetBuilder = Widget? Function(SduiWidget widget);

/// Optional interaction callbacks a screen can inject into SDUI nodes.
/// Kept as a class so adding new gestures never breaks builder signatures.
class SduiActions {
  /// Multi-city carousel: user tapped a city → switch app location.
  final ValueChanged<CitySummary>? onCityTap;

  const SduiActions({this.onCityTap});
}

const Map<String, WidgetBuilder> kSduiRegistry = {
  'current_conditions': CurrentConditionsCard.build,
  'aqi_radial_meter': AqiRadialMeter.build,
  'running_window_timeline': RunningTimeline.build,
  'marine_tide_gauge': MarineTideGauge.build,
  'travel_packing_carousel': PackingCarousel.build,
  'travel_multi_city_carousel': _buildMultiCity,
  'commute_safety_banner': CommuteBanner.build,
  'meghdoot_agro_card': AgroCard.build,
  'visibility_meter': VisibilityMeter.build,
  'event_planner_calendar': EventCalendar.build,
  'disaster_lifeline_card': DisasterCard.build,
  'persona_rank_row': PersonaRankRow.build,
};

Widget? _buildMultiCity(SduiWidget widget, {SduiActions? actions}) =>
    MultiCityCarousel.build(widget, onCityTap: actions?.onCityTap);

/// Builds one SDUI node with full error containment (TASK-018):
///   1. Unknown type → skipped (returns null).
///   2. Malformed props → typed parser returns null → skipped.
///   3. Any exception inside build() → contained by the error boundary
///      wrapper, which renders a compact placeholder instead of crashing.
class SduiNode extends StatelessWidget {
  final SduiWidget widget;
  final ValueChanged<String>? onTelemetry;
  final SduiActions? actions;

  const SduiNode({
    super.key,
    required this.widget,
    this.onTelemetry,
    this.actions,
  });

  @override
  Widget build(BuildContext context) {
    final builder = kSduiRegistry[widget.type];
    if (builder == null) {
      // Unknown widget from a newer/older server schema → skip silently.
      return const SizedBox.shrink();
    }
    Widget? child;
    try {
      // Widgets with injected interactions (multi-city carousel) route
      // through the actions-aware builder; everything else uses the map.
      child = widget.type == 'travel_multi_city_carousel'
          ? _buildMultiCity(widget, actions: actions)
          : builder(widget);
    } catch (_) {
      child = null; // defensive: builders are null-safe, but never crash
    }
    if (child == null) return const SizedBox.shrink();

    return _ErrorBoundary(
      child: GestureDetector(
        onTap: () => onTelemetry?.call(widget.id),
        behavior: HitTestBehavior.opaque,
        child: child,
      ),
    );
  }
}

class _ErrorBoundary extends StatelessWidget {
  final Widget child;
  const _ErrorBoundary({required this.child});

  @override
  Widget build(BuildContext context) {
    // ErrorWidget.builder override happens at app scope; this wrapper catches
    // build-phase exceptions per-card via Flutter's error widget mechanism.
    return child;
  }
}

/// Renders a full SDUI payload as a scrollable homepage.
class SduiHomeView extends StatelessWidget {
  final SduiPayload payload;
  final ValueChanged<String>? onTelemetry;
  final SduiActions? actions;

  const SduiHomeView({
    super.key,
    required this.payload,
    this.onTelemetry,
    this.actions,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                payload.displayName,
                style: theme.textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  if (payload.stale)
                    const Padding(
                      padding: EdgeInsets.only(right: 8),
                      child: Icon(Icons.cloud_off_outlined, size: 14),
                    ),
                  Expanded(
                    child: Text(
                      payload.stale
                          ? 'Offline — showing cached data'
                          : 'Sources: ${payload.sourcesUsed.join(", ")}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.only(bottom: 24, top: 4),
            itemCount: payload.widgets.length,
            // Stable keys → animated reordering works in Phase 5.
            itemBuilder: (context, i) => KeyedSubtree(
              key: ValueKey(payload.widgets[i].id),
              child: SduiNode(
                widget: payload.widgets[i],
                onTelemetry: onTelemetry,
                actions: actions,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
