import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Persona 8 (Event Planners): 10-day color-coded suitability (TASK-038).
class EventCalendar extends StatelessWidget {
  final EventCalendarProps props;

  const EventCalendar({super.key, required this.props});

  static Widget? build(dynamic widget) {
    final props = EventCalendarProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : EventCalendar(props: props);
  }

  Color _color(String suitability) {
    switch (suitability) {
      case 'excellent':
        return const Color(0xFF2E9E4F);
      case 'good':
        return const Color(0xFF9CCC65);
      case 'fair':
        return const Color(0xFFF9A825);
      default:
        return const Color(0xFFE53935);
    }
  }

  @override
  Widget build(BuildContext context) {
    return CardShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const CardTitle(Icons.event_available_outlined, 'EVENT OUTLOOK'),
          const SizedBox(height: 10),
          SizedBox(
            height: 96,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: props.days.length,
              separatorBuilder: (_, __) => const SizedBox(width: 6),
              itemBuilder: (context, i) {
                final d = props.days[i];
                final c = _color(d.suitability);
                return InkWell(
                  borderRadius: BorderRadius.circular(12),
                  onTap: () => _showDayDetail(context, d),
                  child: Container(
                    width: 64,
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    decoration: BoxDecoration(
                      color: c.withValues(alpha: 0.15),
                      border: Border.all(color: c),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          _dayLabel(d.date),
                          style: Theme.of(context).textTheme.labelSmall,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${d.score}',
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: c.darkGreenFix(),
                              ),
                        ),
                        Text(d.suitability, style: Theme.of(context).textTheme.labelSmall),
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

  String _dayLabel(String isoDate) {
    final d = DateTime.tryParse(isoDate);
    if (d == null) return isoDate;
    return '${d.day}/${d.month}';
  }

  /// Tap a day → full detail (score, rain %, condition) — jury-demo friendly.
  void _showDayDetail(BuildContext context, EventDay d) {
    final c = _color(d.suitability);
    showDialog<void>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: Text('Event outlook — ${_dayLabel(d.date)}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(conditionIcon(d.condition), color: c),
                const SizedBox(width: 8),
                Expanded(child: Text(d.condition)),
              ],
            ),
            const SizedBox(height: 12),
            _DetailRow('Suitability score', '${d.score}/100'),
            _DetailRow('Verdict', d.suitability),
            _DetailRow('Chance of rain', '${d.rainPct}%'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogCtx).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  final String label;
  final String value;

  const _DetailRow(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          Text(
            value,
            style: Theme.of(context)
                .textTheme
                .bodyMedium
                ?.copyWith(fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

extension on Color {
  Color darkGreenFix() => Color.lerp(this, Colors.black, 0.25) ?? this;
}
