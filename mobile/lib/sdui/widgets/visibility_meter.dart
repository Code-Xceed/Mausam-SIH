import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Persona 7 (Commuters): satellite-fog visibility meter (TASK-037 interim).
class VisibilityMeter extends StatelessWidget {
  final VisibilityProps props;

  const VisibilityMeter({super.key, required this.props});

  static Widget? fromSdui(dynamic widget) {
    final props = VisibilityProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : VisibilityMeter(props: props);
  }

  @override
  Widget build(BuildContext context) {
    final idx = props.fogIndex.clamp(0.0, 1.0);
    final color = idx < 0.3
        ? const Color(0xFF2E9E4F)
        : idx < 0.6
            ? const Color(0xFFF9A825)
            : const Color(0xFFE53935);
    return CardShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const CardTitle(Icons.visibility_outlined, 'VISIBILITY'),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: LinearProgressIndicator(
                  value: 1 - idx, // more bar = more visible
                  minHeight: 10,
                  borderRadius: BorderRadius.circular(5),
                  color: color,
                  backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                ),
              ),
              const SizedBox(width: 12),
              Text(
                props.visibilityM >= 1000
                    ? '${(props.visibilityM / 1000).toStringAsFixed(1)} km'
                    : '${props.visibilityM} m',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(props.note, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}
