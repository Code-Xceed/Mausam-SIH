import 'dart:async';

import 'package:rxdart/rxdart.dart';

import 'gazetteer.dart';

/// Search state — atomic snapshot avoids out-of-order UI updates.
class SearchResult {
  final String query;
  final List<Town> towns;
  final bool loading;

  const SearchResult({
    required this.query,
    required this.towns,
    required this.loading,
  });
}

/// 500ms-debounced search over the offline gazetteer (TASK-024).
///
/// The legacy Mausam crash: every keystroke fired a network search; responses
/// arrived out of order and a 429 killed the app. Here: local-only, debounced,
/// and `switchMap` CANCELS the previous query when a new one arrives —
/// out-of-order results are impossible by construction.
class SearchService {
  final Gazetteer _gazetteer;
  final _queries = BehaviorSubject<String>.seeded('');
  StreamSubscription<SearchResult>? _sub;

  final _results = BehaviorSubject<SearchResult>.seeded(
    const SearchResult(query: '', towns: [], loading: false),
  );

  SearchService({Gazetteer? gazetteer}) : _gazetteer = gazetteer ?? Gazetteer.instance;

  Stream<SearchResult> get results => _results.stream;

  /// Wire up: call once after gazetteer.load() completes.
  void start() {
    _sub?.cancel();
    _sub = _queries
        .distinct()
        .debounceTime(const Duration(milliseconds: 500))
        .switchMap((q) async* {
      if (q.trim().isEmpty) {
        yield SearchResult(query: q, towns: const [], loading: false);
        return;
      }
      yield SearchResult(query: q, towns: const [], loading: true);
      // Pure local computation — <20ms for 19k towns, no network, no races.
      final towns = _gazetteer.search(q, limit: 8);
      yield SearchResult(query: q, towns: towns, loading: false);
    }).listen(_results.add);
  }

  void submit(String query) => _queries.add(query);

  void dispose() {
    _sub?.cancel();
    _queries.close();
    _results.close();
  }
}
