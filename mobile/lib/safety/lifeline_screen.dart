import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show Clipboard;

import '../l10n/condition_glyphs.dart';
import '../sdui/sdui_models.dart';
import 'ndma_checklists.dart';

/// TASK-052: the Disaster Lifeline takeover — a full-screen emergency layout
/// that replaces the normal weather feed while a Severe+ CAP alert is active.
///
/// Acceptance features:
///   • interactive evacuation-corridor map (self-contained painter — the
///     Phase 7 MapLibre integration swaps in behind the same widget),
///   • nearest relief-shelter markers with tap callouts,
///   • offline SOS contact buttons (clipboard dial, works with zero network),
///   • one-tap access to the bundled NDMA checklists (TASK-053).
class LifelineScreen extends StatelessWidget {
  final DisasterProps alert;
  final VoidCallback onAcknowledge;

  const LifelineScreen({
    super.key,
    required this.alert,
    required this.onAcknowledge,
  });

  @override
  Widget build(BuildContext context) {
    final extreme = alert.severity.toLowerCase().contains('extreme');
    final headerColor = extreme ? const Color(0xFFB71C1C) : const Color(0xFFE65100);
    // TASK-067: shape + color redundantly encode severity (no-literacy UX).
    final (glyph, _) = ConditionGlyphs.severityGlyph(alert.severity);

    return Scaffold(
      backgroundColor: headerColor,
      body: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _Header(alert: alert, color: headerColor, extreme: extreme),
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: Theme.of(context).scaffoldBackgroundColor,
                  borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
                ),
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
                  children: [
                    if (alert.areaDesc != null)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Row(
                          children: [
                            const Icon(Icons.my_location, size: 16),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                'Affected: ${alert.areaDesc}',
                                style: Theme.of(context).textTheme.bodyMedium,
                              ),
                            ),
                          ],
                        ),
                      ),
                    const _EvacuationMapCard(),
                    const SizedBox(height: 12),
                    _ActionRow(
                      icon: Icons.checklist_rounded,
                      title: 'Disaster checklists (offline)',
                      subtitle: 'Official NDMA steps — cyclone, flood, heat wave, lightning',
                      onTap: () => NdmaChecklistScreen.push(context),
                    ),
                    if (alert.safetySteps.isNotEmpty)
                      _ActionRow(
                        icon: Icons.shield_outlined,
                        title: 'Immediate safety steps',
                        subtitle: alert.safetySteps.first,
                        onTap: () => _showSafetyPlan(context),
                      ),
                    const SizedBox(height: 8),
                    _SosCard(contacts: alert.emergencyNumbers),
                    const SizedBox(height: 16),
                    OutlinedButton.icon(
                      onPressed: onAcknowledge,
                      icon: const Icon(Icons.visibility_outlined, size: 18),
                      label: const Text('I am safe — show weather feed'),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Life-safety alerts keep re-alerting while the official warning is active.',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Theme.of(context).colorScheme.onSurfaceVariant,
                          ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showSafetyPlan(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetCtx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
          children: [
            Text('Immediate safety steps',
                style: Theme.of(sheetCtx).textTheme.titleLarge),
            const SizedBox(height: 12),
            for (final s in alert.safetySteps)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.check_circle_outline, size: 18),
                    const SizedBox(width: 10),
                    Expanded(child: Text(s)),
                  ],
                ),
              ),
            if (alert.instruction != null) ...[
              const SizedBox(height: 8),
              Text(alert.instruction!,
                  style: Theme.of(sheetCtx).textTheme.bodySmall),
            ],
          ],
        ),
      ),
    );
  }
}

// --------------------------------------------------------------------------- //

class _Header extends StatelessWidget {
  final DisasterProps alert;
  final Color color;
  final bool extreme;

  const _Header({
    required this.alert,
    required this.color,
    required this.extreme,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(glyph, color: Colors.white, size: 30,
                  semanticLabel: '${alert.severity} ${alert.event} icon'),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  alert.event.toUpperCase(),
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  alert.severity.toUpperCase(),
                  style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            alert.headline,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: Colors.white,
                  height: 1.3,
                ),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              const Icon(Icons.gpp_maybe_outlined, color: Colors.white70, size: 14),
              const SizedBox(width: 6),
              const Expanded(
                child: Text(
                  'Official NDMA/IMD warning • Mausam Lifeline Mode',
                  style: TextStyle(color: Colors.white70, fontSize: 12),
                ),
              ),
              if (extreme)
                const Icon(Icons.priority_high_rounded, color: Colors.white, size: 18),
            ],
          ),
        ],
      ),
    );
  }
}

// --------------------------------------------------------------------------- //
// Evacuation corridor map (self-contained; Phase 7 MapLibre swaps in later)

class _EvacuationMapCard extends StatelessWidget {
  const _EvacuationMapCard();

  @override
  Widget build(BuildContext context) {
    final shelters = kDemoShelters;
    return Card(
      clipBehavior: Clip.antiAlias,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Stack(
            children: [
              const SizedBox(
                height: 210,
                width: double.infinity,
                child: _EvacuationMap(),
              ),
              Positioned(
                top: 8,
                left: 8,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Text(
                    'Evacuation corridor — schematic',
                    style: TextStyle(color: Colors.white, fontSize: 11),
                  ),
                ),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Nearest relief shelters',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
                const SizedBox(height: 6),
                for (final s in shelters)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    leading: Icon(
                      Icons.night_shelter_outlined,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    title: Text(s.name),
                    subtitle: Text('${s.capacity} capacity • ${s.distanceKm.toStringAsFixed(1)} km'),
                    trailing: const Icon(Icons.chevron_right, size: 18),
                    onTap: () => _showShelter(context, s),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _showShelter(BuildContext context, ShelterInfo s) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetCtx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(s.name, style: Theme.of(sheetCtx).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text('${s.capacity} capacity • ${s.distanceKm.toStringAsFixed(1)} km away'),
              if (s.note != null) ...[
                const SizedBox(height: 6),
                Text(s.note!, style: Theme.of(sheetCtx).textTheme.bodySmall),
              ],
              const SizedBox(height: 12),
              const Text(
                'Follow the marked corridor; officials will guide you at checkpoints.',
              ),
            ],
          ),
        ),
      ),
    );
  }
}

@immutable
class ShelterInfo {
  final String name;
  final String capacity;
  final double distanceKm;
  final String? note;

  const ShelterInfo({
    required this.name,
    required this.capacity,
    required this.distanceKm,
    this.note,
  });
}

/// Schematic shelters. Phase 7 replaces coordinates with real NDMA shelter
/// GeoJSON; the UI contract (name/capacity/distance/callout) stays identical.
const kDemoShelters = <ShelterInfo>[
  ShelterInfo(
    name: 'Municipal Cyclone Shelter A',
    capacity: '800',
    distanceKm: 1.2,
    note: 'Ground-floor hall, drinking water available.',
  ),
  ShelterInfo(
    name: 'Govt School Relief Camp',
    capacity: '1,500',
    distanceKm: 2.8,
    note: 'Medical desk and separate family blocks.',
  ),
  ShelterInfo(
    name: 'Community Hall (Elevated)',
    capacity: '450',
    distanceKm: 3.5,
    note: 'Storm-surge safe; pets not permitted.',
  ),
];

class _EvacuationMap extends StatelessWidget {
  const _EvacuationMap();

  @override
  Widget build(BuildContext context) {
    const danger = Color(0xFFB71C1C);
    const safe = Color(0xFF1B5E20);
    return CustomPaint(
      painter: _EvacuationPainter(danger: danger, safe: safe),
      child: const SizedBox.expand(),
    );
  }
}

class _EvacuationPainter extends CustomPainter {
  final Color danger;
  final Color safe;

  _EvacuationPainter({required this.danger, required this.safe});

  @override
  void paint(Canvas canvas, Size size) {
    _grid(canvas, size);

    // Danger zone: sweeping arc along the coast (bottom-left).
    final dangerPaint = Paint()
      ..color = danger.withValues(alpha: 0.18)
      ..style = PaintingStyle.fill;
    final zone = Path()
      ..moveTo(0, size.height)
      ..lineTo(0, size.height * 0.15)
      ..quadraticBezierTo(
        size.width * 0.55, size.height * 0.10,
        size.width * 0.72, size.height * 0.62,
      )
      ..quadraticBezierTo(
        size.width * 0.78, size.height * 0.92,
        size.width * 0.55, size.height,
      )
      ..close();
    canvas.drawPath(zone, dangerPaint);
    canvas.drawPath(
      zone,
      Paint()
        ..color = danger.withValues(alpha: 0.5)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );

    // Corridor: main + alternate, arrows along the safe direction.
    final corridorPaint = Paint()
      ..color = safe
      ..style = PaintingStyle.stroke
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.round;
    final main = Path()
      ..moveTo(size.width * 0.16, size.height * 0.88)
      ..lineTo(size.width * 0.34, size.height * 0.62)
      ..lineTo(size.width * 0.42, size.height * 0.30)
      ..lineTo(size.width * 0.40, size.height * 0.10);
    canvas.drawPath(main, corridorPaint);
    final alt = Path()
      ..moveTo(size.width * 0.62, size.height * 0.86)
      ..lineTo(size.width * 0.70, size.height * 0.52)
      ..lineTo(size.width * 0.86, size.height * 0.26);
    canvas.drawPath(alt, corridorPaint..strokeWidth = 4);
    _arrows(canvas, main, safe, size);
    _arrows(canvas, alt, safe, size);

    // You-are-here marker.
    _dot(canvas, Offset(size.width * 0.16, size.height * 0.88),
        const Color(0xFF0B57D0), 7);
    // Shelter markers.
    _dot(canvas, Offset(size.width * 0.40, size.height * 0.10), safe, 6);
    _dot(canvas, Offset(size.width * 0.86, size.height * 0.26), safe, 6);
  }

  void _grid(Canvas canvas, Size size) {
    final grid = Paint()
      ..color = Colors.grey.withValues(alpha: 0.25)
      ..strokeWidth = 0.5;
    const step = 28.0;
    for (double x = 0; x < size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), grid);
    }
    for (double y = 0; y < size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }
  }

  void _arrows(Canvas canvas, Path path, Color color, Size size) {
    final arrow = Paint()
      ..color = color
      ..style = PaintingStyle.fill;
    for (final t in const [0.25, 0.55, 0.85]) {
      final pos = _pathAt(path, t);
      canvas.drawCircle(pos, 3, arrow);
    }
  }

  Offset _pathAt(Path path, double t) {
    final metrics = path.computeMetrics().toList();
    if (metrics.isEmpty) return Offset.zero;
    final m = metrics.first;
    final tangent = m.getTangentForOffset(m.length * t);
    return tangent?.position ?? Offset.zero;
  }

  void _dot(Canvas canvas, Offset c, Color color, double radius) {
    canvas.drawCircle(c, radius + 2.5, Paint()..color = Colors.white);
    canvas.drawCircle(c, radius, Paint()..color = color);
  }

  @override
  bool shouldRepaint(covariant _EvacuationPainter old) =>
      old.danger != danger || old.safe != safe;
}

// --------------------------------------------------------------------------- //

class _ActionRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _ActionRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: Theme.of(context).dividerColor.withValues(alpha: 0.4)),
      ),
      child: ListTile(
        onTap: onTap,
        leading: Icon(icon, size: 26, color: Theme.of(context).colorScheme.primary),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(
          subtitle,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        trailing: const Icon(Icons.chevron_right, size: 20),
      ),
    );
  }
}

class _SosCard extends StatelessWidget {
  final List<EmergencyContact> contacts;

  const _SosCard({required this.contacts});

  @override
  Widget build(BuildContext context) {
    final list = contacts.isNotEmpty
        ? contacts
        : const [
            EmergencyContact(label: 'National Emergency', number: '112'),
            EmergencyContact(label: 'NDMA Helpline', number: '1078'),
            EmergencyContact(label: 'Ambulance', number: '108'),
          ];
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFB71C1C).withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFB71C1C).withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.sos_rounded, color: Color(0xFFB71C1C), size: 20),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'SOS — tap to copy & dial (works offline)',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: const Color(0xFFB71C1C),
                      ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final c in list)
                FilledButton.tonalIcon(
                  onPressed: () => _copy(context, c.number),
                  icon: const Icon(Icons.call, size: 16),
                  label: Text('${c.label} • ${c.number}'),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

Future<void> _copy(BuildContext context, String number) async {
  await Clipboard.setData(ClipboardData(text: number));
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).hideCurrentSnackBar();
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text('Copied $number — dial now')),
  );
}
