import 'package:flutter/material.dart';

/// Shared styling + mapping helpers for SDUI cards.

const cardRadius = 16.0;

Color aqiColor(String category) {
  switch (category) {
    case 'Good':
      return const Color(0xFF2E9E4F);
    case 'Satisfactory':
      return const Color(0xFF9CCC65);
    case 'Moderate':
      return const Color(0xFFF9A825);
    case 'Poor':
      return const Color(0xFFEF6C00);
    case 'Very Poor':
      return const Color(0xFFE53935);
    case 'Severe':
      return const Color(0xFF8E0000);
    default:
      return const Color(0xFF78909C);
  }
}

Color beachFlagColor(String? flag) {
  switch (flag) {
    case 'green':
      return const Color(0xFF2E9E4F);
    case 'yellow':
      return const Color(0xFFF9A825);
    case 'red':
      return const Color(0xFFE53935);
    default:
      return const Color(0xFF78909C);
  }
}

IconData conditionIcon(String condition) {
  switch (condition) {
    case 'clear':
      return Icons.wb_sunny_outlined;
    case 'partly_cloudy':
      return Icons.partly_cloudy_day_outlined;
    case 'cloudy':
      return Icons.cloud_outlined;
    case 'fog':
    case 'haze':
      return Icons.foggy_outlined;
    case 'drizzle':
      return Icons.grain_outlined;
    case 'rain':
      return Icons.umbrella_outlined;
    case 'thunderstorm':
      return Icons.bolt_outlined;
    case 'hail':
      return Icons.ac_unit_outlined;
    case 'snow':
      return Icons.ac_unit_outlined;
    default:
      return Icons.help_outline_outlined;
  }
}

/// Standard container for every SDUI card.
class CardShell extends StatelessWidget {
  final Widget child;
  final Color? accent;
  final EdgeInsets padding;

  const CardShell({
    super.key,
    required this.child,
    this.accent,
    this.padding = const EdgeInsets.all(16),
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(cardRadius),
        border: Border.all(
          color: (accent ?? theme.colorScheme.outlineVariant).withValues(alpha: 0.4),
        ),
      ),
      child: Padding(padding: padding, child: child),
    );
  }
}

class CardTitle extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color? color;

  const CardTitle(this.icon, this.label, {super.key, this.color});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: color ?? Theme.of(context).colorScheme.primary),
        const SizedBox(width: 6),
        Text(
          label,
          style: Theme.of(context).textTheme.labelLarge?.copyWith(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
        ),
      ],
    );
  }
}
