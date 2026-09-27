import 'package:flutter/material.dart';

import '../state/persona_store.dart';

/// Onboarding (TASK-021): optional persona tags → composer context.
class OnboardingScreen extends StatefulWidget {
  final List<String> initial;
  final ValueChanged<List<String>> onDone;

  const OnboardingScreen({
    super.key,
    required this.initial,
    required this.onDone,
  });

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  late final Set<String> _selected = Set.from(widget.initial);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Spacer(),
              Text(
                'मौसम 2.0',
                style: theme.textTheme.displaySmall?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                'What describes you best?\nYour homepage adapts to it — change anytime.',
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              const Spacer(),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: PersonaStore.allPersonas.entries.map((e) {
                  final selected = _selected.contains(e.key);
                  return FilterChip(
                    selected: selected,
                    label: Text(e.value),
                    avatar: Icon(
                      _iconFor(e.key),
                      size: 18,
                      color: selected ? theme.colorScheme.onPrimary : theme.colorScheme.primary,
                    ),
                    onSelected: (v) => setState(
                      () => v ? _selected.add(e.key) : _selected.remove(e.key),
                    ),
                  );
                }).toList(),
              ),
              const Spacer(),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: FilledButton(
                  onPressed: () => widget.onDone(_selected.toList()),
                  child: const Text('Go'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  IconData _iconFor(String persona) {
    switch (persona) {
      case 'health':
        return Icons.favorite_outline;
      case 'fitness':
        return Icons.directions_run_outlined;
      case 'coastal':
        return Icons.waves;
      case 'travel':
        return Icons.flight_takeoff_outlined;
      case 'family':
        return Icons.family_restroom_outlined;
      case 'farmer':
        return Icons.agriculture;
      case 'commuter':
        return Icons.train_outlined;
      case 'planner':
        return Icons.event_available_outlined;
      default:
        return Icons.person_outline;
    }
  }
}
