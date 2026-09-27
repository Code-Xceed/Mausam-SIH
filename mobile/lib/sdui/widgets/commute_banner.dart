import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Persona 5/7 (Parents & Commuters): commute-window rain/storm banner.
class CommuteBanner extends StatelessWidget {
  final CommuteProps props;

  const CommuteBanner({super.key, required this.props});

  static Widget? fromSdui(dynamic widget) {
    final props = CommuteProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : CommuteBanner(props: props);
  }

  @override
  Widget build(BuildContext context) {
    final isStorm = props.alertLevel == 'storm';
    final color = isStorm ? const Color(0xFFE53935) : const Color(0xFFF9A825);
    return CardShell(
      accent: color,
      child: Row(
        children: [
          Icon(
            isStorm ? Icons.bolt : Icons.umbrella_outlined,
            color: color,
            size: 36,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isStorm ? 'COMMUTE — STORM RISK' : 'COMMUTE — RAIN EXPECTED',
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: color,
                        fontWeight: FontWeight.bold,
                      ),
                ),
                const SizedBox(height: 2),
                Text(props.message, style: Theme.of(context).textTheme.bodyMedium),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            children: [
              Text(
                '~${props.estimatedDelayMin}m',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
              ),
              Text('delay', style: Theme.of(context).textTheme.labelSmall),
              const SizedBox(height: 4),
              Text(
                'from ${props.rainStartHour.toString().padLeft(2, '0')}:00',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: color,
                      fontWeight: FontWeight.w600,
                    ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
