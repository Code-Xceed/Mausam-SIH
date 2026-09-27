import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Diagnostics row — placeholder for the Phase 5 Algorithm Inspector.
/// Shows which personas are active and which engine ranked the feed.
class PersonaRankRow extends StatelessWidget {
  final List<String> personas;
  final String note;

  const PersonaRankRow({super.key, required this.personas, required this.note});

  static Widget? build(dynamic widget) {
    try {
      final props = (widget as dynamic).props as Map<String, dynamic>;
      final ranks = (props['ranks'] as List?) ?? const [];
      final personas = ranks
          .map((e) => (e as Map<String, dynamic>)['persona']?.toString())
          .whereType<String>()
          .toList();
      if (personas.isEmpty) return null;
      return PersonaRankRow(personas: personas, note: props['note']?.toString() ?? '');
    } catch (_) {
      return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
      child: Row(
        children: [
          Icon(Icons.insights_outlined,
              size: 14, color: Theme.of(context).colorScheme.onSurfaceVariant),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              'Ranked for: ${personas.join(", ")} · engine: $note',
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
