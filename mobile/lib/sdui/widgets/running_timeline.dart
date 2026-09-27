import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Persona 2 (Fitness): "Best Running Hours" timeline (TASK-032).
class RunningTimeline extends StatelessWidget {
  final RunningProps props;

  const RunningTimeline({super.key, required this.props});

  static Widget? fromSdui(dynamic widget) {
    final props = RunningProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : RunningTimeline(props: props);
  }

  @override
  Widget build(BuildContext context) {
    return CardShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const CardTitle(Icons.directions_run_outlined, 'BEST RUNNING HOURS'),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: props.windows.map((w) {
              final optimal = w.rating == 'optimal';
              final color = optimal ? const Color(0xFF2E9E4F) : const Color(0xFF9CCC65);
              return Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.15),
                  border: Border.all(color: color),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      optimal ? Icons.favorite_outline : Icons.thumb_up_outlined,
                      size: 14,
                      color: color,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '${_hh(w.startHour)}–${_hh(w.endHour)}'
                      '${w.avgTempC != null ? ' · ${w.avgTempC!.round()}°' : ''}',
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(
                            color: color.darkGreenFix(),
                            fontWeight: FontWeight.w600,
                          ),
                    ),
                  ],
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 8),
          Text(
            'Windows: ≤30°C, ≤85% humidity, <20 km/h wind, rain <40%',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
        ],
      ),
    );
  }

  String _hh(int h) => '${h.toString().padLeft(2, '0')}:00';
}

extension on Color {
  Color darkGreenFix() => Color.lerp(this, Colors.black, 0.25) ?? this;
}
