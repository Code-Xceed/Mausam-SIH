import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

/// Global error containment (TASK-030): no unhandled exception reaches the
/// OS — the legacy app's crash loop is structurally impossible here.
///
/// Strategy: log every error (Phase 5: queue to encrypted telemetry box for
/// batched upload), keep the app running, show friendly UI where possible.
class ErrorBoundary {
  static final _errors = <String>[];
  static int get errorCount => _errors.length;
  static List<String> get recentErrors => List.unmodifiable(_errors);

  static void install() {
    // Framework errors (build/layout/paint).
    FlutterError.onError = (details) {
      FlutterError.presentError(details);
      _record('FRAMEWORK: ${details.exceptionAsString()}');
    };

    // Async/platform errors escaping zones.
    PlatformDispatcher.instance.onError = (error, stack) {
      _record('ASYNC: $error');
      return true; // handled — do not crash the isolate
    };

    // Unknown SDUI widget types or broken builders render as quiet skips.
    ErrorWidget.builder = (details) {
      _record('WIDGET: ${details.exceptionAsString()}');
      return const SizedBox.shrink(); // never the red/grey error screen
    };
  }

  static void _record(String message) {
    final ts = DateTime.now().toIso8601String();
    _errors.add('$ts | $message');
    if (_errors.length > 100) _errors.removeAt(0);
    // Phase 5: enqueue to telemetry_box for batched upload (offline-first).
  }
}
