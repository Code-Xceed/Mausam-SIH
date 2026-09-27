import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Persona 3 (Beachgoers/Surfers): tide sine chart + surf verdict (TASK-033).
class MarineTideGauge extends StatelessWidget {
  final MarineProps props;

  const MarineTideGauge({super.key, required this.props});

  static Widget? build(dynamic widget) {
    final props = MarineProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : MarineTideGauge(props: props);
  }

  String _hhmm(String iso) {
    final t = DateTime.tryParse(iso);
    if (t == null) return iso;
    return '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final flagColor = beachFlagColor(props.beachFlag);
    return CardShell(
      accent: flagColor,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const CardTitle(Icons.waves, 'SEA STATE'),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: flagColor,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  (props.beachFlag ?? '?').toUpperCase(),
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          if (props.tideCurve.length >= 2)
            SizedBox(
              height: 80,
              width: double.infinity,
              child: CustomPaint(
                painter: _TideCurvePainter(
                  points: props.tideCurve,
                  color: Theme.of(context).colorScheme.primary,
                  now: DateTime.now(),
                ),
              ),
            ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 16,
            runSpacing: 6,
            children: [
              _Metric('Wave', props.waveHeightM != null ? '${props.waveHeightM!.toStringAsFixed(1)} m' : '—'),
              _Metric('Swell', props.swellPeriodS != null ? '${props.swellPeriodS!.round()} s' : '—'),
              _Metric('SST', props.sstC != null ? '${props.sstC!.round()}°C' : '—'),
              _Metric('Tide', props.tideState ?? '—'),
              if (props.nextHighTide != null)
                _Metric('Next high', _hhmm(props.nextHighTide!)),
              if (props.nextLowTide != null)
                _Metric('Next low', _hhmm(props.nextLowTide!)),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            props.surfOk ? 'Good surf window 🏄' : 'Surf conditions not ideal',
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
          ),
          if (props.beachNote.isNotEmpty)
            Text(props.beachNote, style: Theme.of(context).textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  final String label;
  final String value;
  const _Metric(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelSmall),
        Text(value, style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class _TideCurvePainter extends CustomPainter {
  final List<TidePoint> points;
  final Color color;
  final DateTime? now;

  _TideCurvePainter({required this.points, required this.color, this.now});

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;
    final heights = points.map((p) => p.heightM).toList();
    final minH = heights.reduce(math.min);
    final maxH = heights.reduce(math.max);
    final range = (maxH - minH).abs() < 0.01 ? 1.0 : maxH - minH;

    double xOf(int i) => i * size.width / (points.length - 1);
    double yOf(int i) =>
        size.height - ((points[i].heightM - minH) / range) * (size.height - 12) - 6;

    final path = Path();
    for (var i = 0; i < points.length; i++) {
      if (i == 0) {
        path.moveTo(xOf(i), yOf(i));
      } else {
        path.lineTo(xOf(i), yOf(i));
      }
    }

    // Soft fill under the curve.
    final fill = Path.from(path)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();
    canvas.drawPath(
      fill,
      Paint()
        ..style = PaintingStyle.fill
        ..color = color.withValues(alpha: 0.12),
    );

    final stroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.5
      ..color = color;
    canvas.drawPath(path, stroke);

    // "Now" marker: the backend curve starts at bucketed-now, so x=0 is now.
    // If `now` is provided, position it by timestamp instead (refresh-safe).
    final t0 = points.first.time.millisecondsSinceEpoch;
    final t1 = points.last.time.millisecondsSinceEpoch;
    final cur = (now ?? DateTime.now()).millisecondsSinceEpoch;
    final frac = t1 > t0 ? (cur - t0) / (t1 - t0) : 0.0;
    final nowX = (frac.clamp(0.0, 1.0)) * size.width;
    // Interpolate the curve's Y at nowX (marker can sit mid-segment when the
    // payload is cached/re-timed).
    final pos = frac.clamp(0.0, 1.0) * (points.length - 1);
    final i0 = pos.floor();
    final i1 = math.min(i0 + 1, points.length - 1);
    final t = pos - i0;
    final nowY = yOf(i0) + (yOf(i1) - yOf(i0)) * t;
    canvas.drawLine(
      Offset(nowX, 0),
      Offset(nowX, size.height),
      Paint()..color = color.withValues(alpha: 0.3),
    );
    canvas.drawCircle(
      Offset(nowX, nowY),
      4,
      Paint()..color = color,
    );
  }

  @override
  bool shouldRepaint(covariant _TideCurvePainter old) =>
      old.points != points || old.now != now;
}
