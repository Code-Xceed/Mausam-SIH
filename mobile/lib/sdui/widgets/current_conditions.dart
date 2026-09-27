import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

class CurrentConditionsCard extends StatelessWidget {
  final CurrentProps props;

  const CurrentConditionsCard({super.key, required this.props});

  static Widget? build(dynamic widget) {
    final props = CurrentProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : CurrentConditionsCard(props: props);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return CardShell(
      child: Row(
        children: [
          Icon(
            conditionIcon(props.condition),
            size: 56,
            color: theme.colorScheme.primary,
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${props.temperatureC.round()}°',
                      style: theme.textTheme.displayMedium
                          ?.copyWith(fontWeight: FontWeight.w300),
                    ),
                    const SizedBox(width: 8),
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Text(
                        props.feelsLikeC != null
                            ? 'feels ${props.feelsLikeC!.round()}°'
                            : '',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ),
                  ],
                ),
                Text(props.conditionText, style: theme.textTheme.bodyMedium),
                const SizedBox(height: 8),
                Row(
                  children: [
                    _Metric(icon: Icons.water_drop_outlined, value: '${props.humidityPct.round()}%'),
                    const SizedBox(width: 16),
                    _Metric(icon: Icons.air_outlined, value: '${props.windKmph.round()} km/h'),
                    if (props.uvIndex != null) ...[
                      const SizedBox(width: 16),
                      _Metric(
                        icon: Icons.wb_twilight_outlined,
                        value: 'UV ${props.uvIndex!.toStringAsFixed(1)}',
                      ),
                    ],
                  ],
                ),
                if (props.uvAdvice != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    props.uvAdvice!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  final IconData icon;
  final String value;

  const _Metric({required this.icon, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 16, color: Theme.of(context).colorScheme.onSurfaceVariant),
        const SizedBox(width: 4),
        Text(value, style: Theme.of(context).textTheme.bodyMedium),
      ],
    );
  }
}
