import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Multi-city summary card for travelers (TASK-034 completion): home + saved
/// cities side by side; tap a city → app switches location.
class MultiCityCarousel extends StatelessWidget {
  final List<CitySummary> cities;
  final ValueChanged<CitySummary>? onCityTap;

  const MultiCityCarousel({super.key, required this.cities, this.onCityTap});

  static Widget? build(dynamic widget, {ValueChanged<CitySummary>? onCityTap}) {
    try {
      final props = (widget as dynamic).props as Map<String, dynamic>;
      final cities = ((props['cities'] as List?) ?? const [])
          .map((e) => CitySummary.tryParse(e as Map<String, dynamic>))
          .whereType<CitySummary>()
          .toList();
      if (cities.length < 2) return null;
      return MultiCityCarousel(cities: cities, onCityTap: onCityTap);
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    return CardShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const CardTitle(Icons.flight_takeoff_outlined, 'YOUR CITIES'),
          const SizedBox(height: 10),
          SizedBox(
            height: 108,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: cities.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (context, i) {
                final c = cities[i];
                return InkWell(
                  borderRadius: BorderRadius.circular(12),
                  onTap: onCityTap == null ? null : () => onCityTap!(c),
                  child: Container(
                    width: 116,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                c.name,
                                style: Theme.of(context)
                                    .textTheme
                                    .labelLarge
                                    ?.copyWith(fontWeight: FontWeight.w600),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                        const Spacer(),
                        Icon(conditionIcon(c.condition), size: 28),
                        Text(
                          '${c.tempMaxC.round()}° / ${c.tempMinC.round()}°',
                          style: Theme.of(context).textTheme.labelLarge,
                        ),
                        Text(
                          'rain ${c.rainPct}%',
                          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                color: Theme.of(context).colorScheme.onSurfaceVariant,
                              ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
