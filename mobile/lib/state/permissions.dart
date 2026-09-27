import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// TASK-078: runtime permission handling with graceful degradation.
///
/// Design contract: the app NEVER blocks on a permission. Coarse location
/// denied → fall back to the saved/searched city; notifications denied →
/// in-app disaster cards still work (they always have — Lifeline triggers
/// from the feed, push is a convenience door).
class PermissionsHelper {
  static const _channel = MethodChannel('mausam/location');

  /// Whether the platform has coarse location granted (no prompt).
  static Future<bool> hasCoarseLocation() async {
    try {
      return await _channel.invokeMethod<bool>('hasCoarsePermission') ?? false;
    } on MissingPluginException {
      return false;
    } catch (_) {
      return false;
    }
  }

  /// Last coarse fix from the platform (already truncated to 0.05° natively
  /// so the Dart layer never sees better-than-coarse data).
  static Future<(double, double)?> lastCoarseFix() async {
    try {
      final raw = await _channel.invokeMethod<List>('lastCoarseFix');
      if (raw == null || raw.length < 2) return null;
      return ((raw[0] as num).toDouble(), (raw[1] as num).toDouble());
    } on MissingPluginException {
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Shows the "why we need this" rationale for disaster alerts, then the
  /// OS permission dialog happens natively. Returns whether the user wants
  /// to proceed (the OS dialog itself is triggered by the native side when
  /// the user next taps "Locate me").
  static Future<bool> showNotificationRationale(
    BuildContext context, {
    String place = 'your area',
  }) async {
    final result = await showDialog<bool>(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        icon: const Icon(Icons.notifications_active),
        title: const Text('Allow disaster alerts?'),
        content: Text(
          'Mausam sends official NDMA/IMD Red warnings for $place — cyclone, '
          'flood, heat wave. These can wake your phone in an emergency and '
          'show a full-screen Lifeline view.\n\n'
          'You can change this later in system settings. The app works fully '
          'without notifications — in-app alerts always fire.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogCtx).pop(false),
            child: const Text('Not now'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogCtx).pop(true),
            child: const Text('Allow'),
          ),
        ],
      ),
    );
    return result ?? false;
  }
}
