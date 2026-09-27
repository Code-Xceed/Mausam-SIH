import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Persona 9 (Disaster Lifeline): red takeover card — pinned to position 0
/// by the composer whenever a Severe+ CAP alert intersects the user's area.
class DisasterCard extends StatelessWidget {
  final DisasterProps props;

  const DisasterCard({super.key, required this.props});

  static Widget? fromSdui(dynamic widget) {
    final props = DisasterProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : DisasterCard(props: props);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.fromLTRB(12, 6, 12, 6),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFFB71C1C),
        borderRadius: BorderRadius.circular(cardRadius),
      ),
      child: DefaultTextStyle(
        style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.white),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.crisis_alert, color: Colors.white, size: 28),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    props.event.toUpperCase(),
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                        ),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    props.severity.toUpperCase(),
                    style: const TextStyle(
                      color: Color(0xFFB71C1C),
                      fontWeight: FontWeight.bold,
                      fontSize: 11,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              props.headline,
              style: Theme.of(context).textTheme.titleSmall?.copyWith(color: Colors.white),
            ),
            if (props.areaDesc != null) ...[
              const SizedBox(height: 4),
              Text(
                'Area: ${props.areaDesc}',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Colors.white.withValues(alpha: 0.85),
                    ),
              ),
            ],
            if (props.safetySteps.isNotEmpty) ...[
              const SizedBox(height: 12),
              ...props.safetySteps.take(4).map(
                    (s) => Padding(
                      padding: const EdgeInsets.only(bottom: 4),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.check_circle_outline, size: 16, color: Colors.white),
                          const SizedBox(width: 6),
                          Expanded(child: Text(s, style: const TextStyle(fontSize: 13))),
                        ],
                      ),
                    ),
                  ),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              children: props.emergencyNumbers
                  .map((c) => ActionChip(
                        backgroundColor: Colors.white,
                        avatar: const Icon(Icons.call, size: 16, color: Color(0xFFB71C1C)),
                        label: Text(
                          '${c.label} ${c.number}',
                          style: const TextStyle(
                            color: Color(0xFFB71C1C),
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        onPressed: () async {
                          // Dial-out requires the url_launcher/telephony plugin;
                          // Phase 6 wires real dialing. Copy for now — works offline.
                          await Clipboard.setData(ClipboardData(text: c.number));
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(content: Text('Copied ${c.number} — dial now')),
                            );
                          }
                        },
                      ))
                  .toList(),
            ),
          ],
        ),
      ),
    );
  }
}
