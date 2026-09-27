import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Persona 4 (Travelers): packing engine + 3-day strip (TASK-034).
class PackingCarousel extends StatelessWidget {
  final PackingProps props;

  const PackingCarousel({super.key, required this.props});

  static Widget? fromSdui(dynamic widget) {
    final props = PackingProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : PackingCarousel(props: props);
  }

  @override
  Widget build(BuildContext context) {
    return CardShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const CardTitle(Icons.luggage_outlined, 'TRAVEL PACKING'),
          const SizedBox(height: 10),
          SizedBox(
            height: 92,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: props.days.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (context, i) {
                final d = props.days[i];
                return Container(
                  width: 108,
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        _weekday(d.date),
                        style: Theme.of(context).textTheme.labelMedium,
                      ),
                      Icon(conditionIcon(d.condition), size: 26),
                      Text(
                        '${d.tempMaxC.round()}° / ${d.tempMinC.round()}°',
                        style: Theme.of(context).textTheme.labelLarge,
                      ),
                      Text(
                        'rain ${d.rainPct}%',
                        style: Theme.of(context).textTheme.labelSmall,
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
          if (props.packing.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: props.packing
                  .map((item) => Chip(
                        avatar: const Icon(Icons.check_box_outline_blank, size: 16),
                        label: Text(item, style: const TextStyle(fontSize: 12)),
                        visualDensity: VisualDensity.compact,
                      ))
                  .toList(),
            ),
          ],
        ],
      ),
    );
  }

  String _weekday(String isoDate) {
    final d = DateTime.tryParse(isoDate);
    if (d == null) return isoDate;
    return ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][d.weekday - 1];
  }
}
