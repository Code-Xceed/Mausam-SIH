import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../sdui_models.dart';
import 'common.dart';

/// Persona 1 (Health-Conscious): animated radial AQI gauge (TASK-031).
class AqiRadialMeter extends StatelessWidget {
  final AqiProps props;

  const AqiRadialMeter({super.key, required this.props});

  static Widget? fromSdui(dynamic widget) {
    final props = AqiProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : AqiRadialMeter(props: props);
  }

  static Widget? buildAnimated(dynamic widget) {
    final props = AqiProps.tryParse((widget as dynamic).props as Map<String, dynamic>);
    return props == null ? null : _AqiRadialMeterAnimated(props: props);
  }

  @override
  Widget build(BuildContext context) {
    final color = aqiColor(props.category);
    return CardShell(
      accent: color,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const CardTitle(Icons.air, 'AIR QUALITY'),
          const SizedBox(height: 12),
          Row(
            children: [
              SizedBox(
                width: 120,
                height: 120,
                child: CustomPaint(
                  painter: _AqiGaugePainter(
                    value: props.aqi.clamp(0, 500),
                    fraction: 1.0,
                    color: color,
                  ),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '${props.aqi}',
                          style: Theme.of(context)
                              .textTheme
                              .headlineMedium
                              ?.copyWith(fontWeight: FontWeight.bold),
                        ),
                        Text(
                          props.category,
                          style: Theme.of(context).textTheme.labelSmall,
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (props.dominatingPollutant != null)
                      _Row(label: 'Dominant', value: props.dominatingPollutant!.toUpperCase()),
                    if (props.pm25 != null)
                      _Row(label: 'PM2.5', value: '${props.pm25!.toStringAsFixed(1)} µg/m³'),
                    if (props.pm10 != null)
                      _Row(label: 'PM10', value: '${props.pm10!.toStringAsFixed(1)} µg/m³'),
                  ],
                ),
              ),
            ],
          ),
          if (props.advice.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              props.advice,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: color.darken(),
                    fontWeight: FontWeight.w500,
                  ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Animated variant: sweeps the gauge arc from 0 → AQI on first appearance.
class _AqiRadialMeterAnimated extends StatefulWidget {
  final AqiProps props;

  const _AqiRadialMeterAnimated({required this.props});

  @override
  State<_AqiRadialMeterAnimated> createState() => _AqiRadialMeterAnimatedState();
}

class _AqiRadialMeterAnimatedState extends State<_AqiRadialMeterAnimated>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctl;
  late final CurvedAnimation _curve;

  @override
  void initState() {
    super.initState();
    _ctl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    _curve = CurvedAnimation(parent: _ctl, curve: Curves.easeOutCubic);
    _ctl.forward();
  }

  @override
  void didUpdateWidget(covariant _AqiRadialMeterAnimated old) {
    super.didUpdateWidget(old);
    // New AQI value (e.g. pull-to-refresh) → re-sweep from current progress.
    if (old.props.aqi != widget.props.aqi) _ctl.forward(from: 0);
  }

  @override
  void dispose() {
    _curve.dispose();
    _ctl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = aqiColor(widget.props.category);
    return CardShell(
      accent: color,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const CardTitle(Icons.air, 'AIR QUALITY'),
          const SizedBox(height: 12),
          Row(
            children: [
              SizedBox(
                width: 120,
                height: 120,
                child: AnimatedBuilder(
                  animation: _curve,
                  builder: (context, child) => CustomPaint(
                    painter: _AqiGaugePainter(
                      value: widget.props.aqi.clamp(0, 500),
                      fraction: _curve.value,
                      color: color,
                    ),
                    child: child,
                  ),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '${widget.props.aqi}',
                          style: Theme.of(context)
                              .textTheme
                              .headlineMedium
                              ?.copyWith(fontWeight: FontWeight.bold),
                        ),
                        Text(
                          widget.props.category,
                          style: Theme.of(context).textTheme.labelSmall,
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (widget.props.dominatingPollutant != null)
                      _Row(
                        label: 'Dominant',
                        value: widget.props.dominatingPollutant!.toUpperCase(),
                      ),
                    if (widget.props.pm25 != null)
                      _Row(
                        label: 'PM2.5',
                        value: '${widget.props.pm25!.toStringAsFixed(1)} µg/m³',
                      ),
                    if (widget.props.pm10 != null)
                      _Row(
                        label: 'PM10',
                        value: '${widget.props.pm10!.toStringAsFixed(1)} µg/m³',
                      ),
                  ],
                ),
              ),
            ],
          ),
          if (widget.props.advice.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              widget.props.advice,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: color.darken(),
                    fontWeight: FontWeight.w500,
                  ),
            ),
          ],
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  final String label;
  final String value;

  const _Row({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          Text(value,
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _AqiGaugePainter extends CustomPainter {
  final int value;
  final double fraction;
  final Color color;

  _AqiGaugePainter({required this.value, required this.fraction, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2 - 6;
    const sweep = math.pi * 1.5;
    const start = -math.pi * 0.75;

    final track = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round
      ..color = Colors.grey.withValues(alpha: 0.25);
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), start, sweep, false, track);

    final fraction = (value / 500).clamp(0.02, 1.0) * this.fraction;
    final arc = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round
      ..color = color;
    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), start, sweep * fraction, false, arc);
  }

  @override
  bool shouldRepaint(covariant _AqiGaugePainter old) =>
      old.value != value || old.color != color || old.fraction != fraction;
}

extension on Color {
  Color darken([double amount = .3]) {
    return Color.lerp(this, Colors.black, amount) ?? this;
  }
}
