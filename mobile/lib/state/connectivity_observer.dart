import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';

/// Connection state exposed to the UI (TASK-029).
enum ConnState { live, offline }

/// Real-time network listener with a subtle visual contract: the app shows a
/// small offline chip — never an interruption. Data layer stays local-first,
/// so this is informational, not functional, gating.
class ConnectivityObserver {
  final _controller = BehaviorSubject<ConnState>.seeded(ConnState.live);
  StreamSubscription<List<ConnectivityResult>>? _sub;

  /// Live connectivity alone can't confirm the gateway is reachable, so the
  /// last successful fetch timestamp sharpens this: backend freshness check
  /// happens in the repository; here we track link state only.
  Stream<ConnState> get stream => _controller.stream;
  ConnState get current => _controller.value;

  void start() {
    _sub?.cancel();
    _sub = Connectivity().onConnectivityChanged.listen((results) {
      final hasLink = results.any((r) => r != ConnectivityResult.none);
      _controller.add(hasLink ? ConnState.live : ConnState.offline);
    });
    // Initial check.
    Connectivity().checkConnectivity().then((results) {
      final hasLink = results.any((r) => r != ConnectivityResult.none);
      _controller.add(hasLink ? ConnState.live : ConnState.offline);
    });
  }

  void dispose() {
    _sub?.cancel();
    _controller.close();
  }
}

// Minimal BehaviorSubject to avoid importing rxdart here just for two members.
class BehaviorSubject<T> {
  T _value;
  final _controller = StreamController<T>.broadcast();

  BehaviorSubject(T initial) : _value = initial;

  T get value => _value;
  Stream<T> get stream => _controller.stream;

  void add(T value) {
    _value = value;
    _controller.add(value);
  }

  void close() => _controller.close();
}
