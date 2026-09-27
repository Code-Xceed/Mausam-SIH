import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart'
    show Clipboard, ClipboardData, rootBundle;

import '../sdui/sdui_models.dart' show EmergencyContact;

/// TASK-053: NDMA disaster preparedness checklists — bundled inside the app
/// binary so life-safety steps render with ZERO connectivity (acceptance
/// criterion). Content mirrors official NDMA public guidance for the four
/// highest-mortality Indian hazards: cyclone, flood, heat wave, lightning.
class NdmaChecklists {
  final String version;
  final List<ChecklistHazard> hazards;
  final List<EmergencyContact> emergencyNumbers;

  const NdmaChecklists({
    required this.version,
    required this.hazards,
    required this.emergencyNumbers,
  });

  static NdmaChecklists? _cached;

  /// Loads once per process; asset reads are local I/O — works in airplane
  /// mode. Returns a safe empty instance rather than throwing if the asset
  /// were ever corrupted (defensive, mirrors SDUI parsing philosophy).
  static Future<NdmaChecklists> load() async {
    final cached = _cached;
    if (cached != null) return cached;
    try {
      final raw =
          await rootBundle.loadString('assets/checklists/ndma_checklists.json');
      final parsed = NdmaChecklists._parse(
        jsonDecode(raw) as Map<String, dynamic>,
      );
      _cached = parsed;
      return parsed;
    } catch (_) {
      final empty = NdmaChecklists(version: '0', hazards: const [], emergencyNumbers: const []);
      _cached = empty;
      return empty;
    }
  }

  factory NdmaChecklists._parse(Map<String, dynamic> json) {
    final raw = (json['checklists'] as Map<String, dynamic>?) ?? const {};
    final hazards = <ChecklistHazard>[];
    for (final entry in raw.entries) {
      final h = ChecklistHazard.tryParse(entry.key, entry.value);
      if (h != null) hazards.add(h);
    }
    return NdmaChecklists(
      version: json['version']?.toString() ?? '0',
      hazards: hazards,
      emergencyNumbers: ((json['emergency_numbers'] as List?) ?? const [])
          .map((e) => EmergencyContact.tryParse(e as Map<String, dynamic>))
          .whereType<EmergencyContact>()
          .toList(),
    );
  }
}

@immutable
class ChecklistHazard {
  final String key;
  final String title;
  final IconData icon;
  final List<String> before;
  final List<String> during;
  final List<String> after;

  const ChecklistHazard({
    required this.key,
    required this.title,
    required this.icon,
    required this.before,
    required this.during,
    required this.after,
  });

  static ChecklistHazard? tryParse(String key, dynamic raw) {
    if (raw is! Map<String, dynamic>) return null;
    final title = raw['title']?.toString();
    if (title == null || title.isEmpty) return null;
    List<String> steps(String field) => ((raw[field] as List?) ?? const [])
        .map((e) => e.toString())
        .where((e) => e.isNotEmpty)
        .toList();
    return ChecklistHazard(
      key: key,
      title: title,
      icon: _iconFor(raw['icon']?.toString() ?? key),
      before: steps('before'),
      during: steps('during'),
      after: steps('after'),
    );
  }

  static IconData _iconFor(String key) {
    switch (key) {
      case 'cyclone':
        return Icons.cyclone;
      case 'flood':
        return Icons.flood;
      case 'heat':
        return Icons.thermostat;
      case 'lightning':
        return Icons.bolt;
      default:
        return Icons.warning_amber_outlined;
    }
  }
}

/// Full-screen offline checklist browser. Pushed from the lifeline takeover,
/// the home app bar, or the drawer — network state is irrelevant by design.
class NdmaChecklistScreen extends StatelessWidget {
  final NdmaChecklists data;

  const NdmaChecklistScreen({super.key, required this.data});

  static Future<void> push(BuildContext context) async {
    final data = await NdmaChecklists.load();
    if (!context.mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => NdmaChecklistScreen(data: data)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return DefaultTabController(
      length: data.hazards.length,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Disaster Checklists'),
          bottom: data.hazards.isEmpty
              ? null
              : TabBar(
                  isScrollable: true,
                  tabAlignment: TabAlignment.start,
                  tabs: [
                    for (final h in data.hazards)
                      Tab(icon: Icon(h.icon, size: 20), text: h.title),
                  ],
                ),
        ),
        body: data.hazards.isEmpty
            ? const Center(child: Text('Checklists unavailable.'))
            : TabBarView(
                children: [
                  for (final h in data.hazards) _HazardChecklist(hazard: h),
                ],
              ),
        bottomNavigationBar: data.emergencyNumbers.isEmpty
            ? null
            : SafeArea(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 4, 12, 8),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 4,
                    children: [
                      for (final c in data.emergencyNumbers)
                        ActionChip(
                          avatar: const Icon(Icons.call, size: 16),
                          label: Text('${c.label} ${c.number}'),
                          onPressed: () => _copyNumber(context, c),
                        ),
                    ],
                  ),
                ),
              ),
      ),
    );
  }

  static void _copyNumber(BuildContext context, EmergencyContact c) async {
    await Clipboard.setData(ClipboardData(text: c.number));
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('Copied ${c.number} — dial from any phone (works offline)')),
    );
  }
}

class _HazardChecklist extends StatelessWidget {
  final ChecklistHazard hazard;

  const _HazardChecklist({required this.hazard});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        Row(
          children: [
            Icon(hazard.icon, size: 32, color: theme.colorScheme.primary),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                '${hazard.title} — official NDMA steps',
                style: theme.textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          'Reads fully offline — bundled in the app, no network needed.',
          style: theme.textTheme.bodySmall
              ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
        _Phase(title: 'BEFORE the event', steps: hazard.before, color: Colors.blueGrey),
        _Phase(title: 'DURING — act now', steps: hazard.during, color: const Color(0xFFB71C1C)),
        _Phase(title: 'AFTER — stay safe', steps: hazard.after, color: Colors.green.shade800),
      ],
    );
  }
}

class _Phase extends StatelessWidget {
  final String title;
  final List<String> steps;
  final Color color;

  const _Phase({required this.title, required this.steps, required this.color});

  @override
  Widget build(BuildContext context) {
    if (steps.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 18, bottom: 6),
          child: Text(
            title,
            style: theme.textTheme.titleSmall?.copyWith(
              color: color,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.5,
            ),
          ),
        ),
        for (var i = 0; i < steps.length; i++)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 22,
                  height: 22,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: color, width: 1.5),
                  ),
                  child: Text(
                    '${i + 1}',
                    style: TextStyle(
                        fontSize: 11, fontWeight: FontWeight.bold, color: color),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    steps[i],
                    style: theme.textTheme.bodyMedium?.copyWith(height: 1.35),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
