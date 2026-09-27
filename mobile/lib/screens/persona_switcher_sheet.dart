import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../state/persona_store.dart';

/// Persona metadata from the server (SDUI principle: adding a persona never
/// needs an app release). Falls back to the bundled static map offline.
class PersonaInfo {
  final String key;
  final String label;
  final String tagline;

  const PersonaInfo({required this.key, required this.label, required this.tagline});

  static PersonaInfo? tryParse(Map<String, dynamic> j) {
    final k = j['key']?.toString();
    if (k == null) return null;
    return PersonaInfo(
      key: k,
      label: j['label']?.toString() ?? k,
      tagline: j['tagline']?.toString() ?? '',
    );
  }
}

/// TASK-039: tap a persona → homepage instantly re-renders. No app restart.
class PersonaSwitcherSheet extends StatefulWidget {
  final String activeKey;
  final ValueChanged<String> onSwitch;
  final VoidCallback? onOpenCustomMix;

  const PersonaSwitcherSheet({
    super.key,
    required this.activeKey,
    required this.onSwitch,
    this.onOpenCustomMix,
  });

  /// Convenience: show and return the chosen persona key (null = dismissed).
  static Future<String?> show(
    BuildContext context, {
    required String activeKey,
    VoidCallback? onOpenCustomMix,
  }) {
    return showModalBottomSheet<String>(
      context: context,
      builder: (_) => PersonaSwitcherSheet(
        activeKey: activeKey,
        onSwitch: (k) => Navigator.of(context).pop(k),
        onOpenCustomMix: onOpenCustomMix,
      ),
    );
  }

  @override
  State<PersonaSwitcherSheet> createState() => _PersonaSwitcherSheetState();
}

class _PersonaSwitcherSheetState extends State<PersonaSwitcherSheet> {
  List<PersonaInfo> _personas = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    // Instant local fill, then server refresh.
    setState(() {
      _personas = PersonaStore.allPersonas.entries
          .map((e) => PersonaInfo(key: e.key, label: e.value, tagline: ''))
          .toList();
      _loading = false;
    });
    try {
      final base = const String.fromEnvironment(
        'BACKEND_URL',
        defaultValue: 'http://10.0.2.2:8000',
      );
      final res = await http
          .get(Uri.parse('$base/v1/personas'))
          .timeout(const Duration(seconds: 3));
      if (res.statusCode == 200 && mounted) {
        final list = ((jsonDecode(res.body)
                as Map<String, dynamic>)['personas'] as List?)
            ?? const [];
        final parsed = list
            .map((e) => PersonaInfo.tryParse(e as Map<String, dynamic>))
            .whereType<PersonaInfo>()
            .toList();
        if (parsed.isNotEmpty) setState(() => _personas = parsed);
      }
    } catch (_) {/* offline: local list already shown */}
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('Switch persona', style: theme.textTheme.titleLarge),
                const Spacer(),
                if (widget.onOpenCustomMix != null)
                  TextButton(
                    onPressed: widget.onOpenCustomMix,
                    child: const Text('Custom mix'),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              'Tap once — the homepage re-assembles instantly',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            Flexible(
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: _personas.length,
                itemBuilder: (context, i) {
                  final p = _personas[i];
                  final active = p.key == widget.activeKey;
                  return ListTile(
                    leading: Icon(
                      _iconFor(p.key),
                      color: active ? theme.colorScheme.primary : null,
                    ),
                    title: Text(
                      p.label,
                      style: active
                          ? TextStyle(fontWeight: FontWeight.bold, color: theme.colorScheme.primary)
                          : null,
                    ),
                    subtitle: p.tagline.isEmpty ? null : Text(p.tagline),
                    trailing: active
                        ? const Icon(Icons.check_circle_rounded)
                        : const Icon(Icons.chevron_right),
                    onTap: () => widget.onSwitch(p.key),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
