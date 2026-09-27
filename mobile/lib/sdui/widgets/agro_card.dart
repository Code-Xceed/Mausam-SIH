import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Persona 6 (Farmers): Meghdoot-style block agro advisory (TASK-036).
class AgroCard extends StatelessWidget {
  final AgroProps props;

  const AgroCard({super.key, required this.props});

  static Widget? fromSdui(dynamic widget) {
    final props = AgroProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : AgroCard(props: props);
  }

  @override
  Widget build(BuildContext context) {
    return CardShell(
      accent: const Color(0xFF2E7D32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const CardTitle(Icons.agriculture, 'AGRO ADVISORY'),
              if (props.frostRisk)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0xFF90A4AE),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Text(
                    'FROST RISK',
                    style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                ),
            ],
          ),
          Text(
            '${props.blockName}${props.amfuName != null ? ' · ${props.amfuName}' : ''}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 10),
          ...props.advisories.take(3).map(
                (a) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('• '),
                      Expanded(
                        child: Text(
                          a,
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
          if (props.soilMoisturePct != null) ...[
            const SizedBox(height: 4),
            Row(
              children: [
                SizedBox(
                  width: 120,
                  child: LinearProgressIndicator(
                    value: props.soilMoisturePct! / 100,
                    minHeight: 8,
                    borderRadius: BorderRadius.circular(4),
                    color: props.soilMoisturePct! < 25
                        ? const Color(0xFFEF6C00)
                        : const Color(0xFF2E9E4F),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  'Soil ${props.soilMoisturePct!.round()}%',
                  style: Theme.of(context).textTheme.labelMedium,
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
