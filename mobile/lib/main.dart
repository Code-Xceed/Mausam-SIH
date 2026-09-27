import 'package:flutter/material.dart';
import 'package:hive_ce_flutter/hive_flutter.dart';

import 'data/favorites_repository.dart';
import 'screens/onboarding_screen.dart';
import 'screens/persona_switcher_sheet.dart';
import 'screens/search_screen.dart';
import 'search/gazetteer.dart';
import 'sdui/sdui_models.dart';
import 'sdui/sdui_registry.dart';
import 'sdui/sdui_repository.dart';
import 'state/connectivity_observer.dart';
import 'state/error_boundary.dart';
import 'state/persona_store.dart';
import 'storage/hive_manager.dart';

/// Mausam Next-Gen — Phase 3 client: offline-first resilience (debounced
/// local search, encrypted favorites dual-write, graceful connectivity).
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  ErrorBoundary.install(); // zero-crash guarantee (TASK-030)
  await HiveManager.init(); // all boxes open before UI (TASK-027)
  runApp(const MausamApp());
}

class MausamApp extends StatelessWidget {
  const MausamApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Mausam Next-Gen',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF0B57D0),
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorSchemeSeed: const Color(0xFF0B57D0),
        brightness: Brightness.dark,
        useMaterial3: true,
      ),
      home: const HomeGate(),
    );
  }
}

/// Chooses onboarding vs homepage based on saved persona state.
class HomeGate extends StatefulWidget {
  const HomeGate({super.key});

  @override
  State<HomeGate> createState() => _HomeGateState();
}

class _HomeGateState extends State<HomeGate> {
  final _store = PersonaStore();
  List<String>? _personas;
  bool? _onboarded;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final explicit = await _store.loadExplicit();
    if (!mounted) return;
    setState(() {
      _onboarded = explicit != null;
      _personas = explicit ?? const ['health', 'commuter'];
    });
  }

  @override
  Widget build(BuildContext context) {
    final personas = _personas;
    final onboarded = _onboarded;
    if (personas == null || onboarded == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (!onboarded) {
      return OnboardingScreen(
        initial: personas,
        onDone: (selected) async {
          final next = selected.isEmpty ? const ['health', 'commuter'] : selected;
          await _store.save(next);
          if (!mounted) return;
          setState(() {
            _personas = next;
            _onboarded = true;
          });
        },
      );
    }
    return HomeScreen(store: _store, personas: personas);
  }
}

class HomeScreen extends StatefulWidget {
  final PersonaStore store;
  final List<String> personas;

  const HomeScreen({super.key, required this.store, required this.personas});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _repo = SduiRepository();
  final _favorites = FavoritesRepository();
  final _connectivity = ConnectivityObserver();
  SduiPayload? _payload;
  String? _error;
  (double, double)? _coords;
  String _placeLabel = 'New Delhi';
  ConnState _conn = ConnState.live;
  List<FavoriteLocation> _favs = const [];
  /// Live persona mix — starts from the constructor value but changes
  /// in place via the quick-switch sheet (no route churn, no restart).
  late List<String> _personas = List.of(widget.personas);

  @override
  void initState() {
    super.initState();
    _connectivity.start();
    _connectivity.stream.listen((s) {
      if (mounted) setState(() => _conn = s);
    });
    _bootstrap();
  }

  @override
  void dispose() {
    _connectivity.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    // Warm the gazetteer in the background (search ready in <200ms).
    Gazetteer.instance.load();

    var coords = await widget.store.loadLocation();
    coords ??= (28.6139, 77.2090);
    _placeLabel = await widget.store.loadLabel() ?? 'New Delhi';
    await widget.store.saveLocation(coords.$1, coords.$2);
    if (!mounted) return;
    setState(() {
      _coords = coords;
      _favs = _favorites.allSync(); // instant local render
    });
    await _load();
  }

  Future<void> _load() async {
    final coords = _coords;
    if (coords == null) return;
    try {
      // Multi-city carousel (TASK-034): favorite cities (minus current)
      // travel to the backend as lat:lon pairs, max 5.
      final extras = _favorites
          .allSync()
          .where((f) => f.lat != coords.$1 || f.lon != coords.$2)
          .take(5)
          .map((f) => (f.lat, f.lon))
          .toList();
      final payload = await _repo.loadHome(
        lat: coords.$1,
        lon: coords.$2,
        personas: _personas,
        cities: extras,
      );
      if (!mounted) return;
      setState(() => _payload = payload);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    }
  }

  Future<void> _refresh() => _load();

  void _openSearch() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => SearchScreen(
          onTownSelected: (town) async {
            Navigator.of(context).pop();
            await widget.store.saveLocation(town.lat, town.lon);
            await widget.store.saveLabel(town.name);
            if (!mounted) return;
            setState(() {
              _coords = (town.lat, town.lon);
              _placeLabel = town.name;
              _payload = null;
            });
            _load();
          },
        ),
      ),
    );
  }

  void _toggleFavorite() {
    final coords = _coords;
    if (coords == null) return;
    if (_favorites.isFavorite(_placeLabel, '')) {
      _favorites.remove(_placeLabel, '');
    } else {
      _favorites.add(
        FavoriteLocation(
          name: _placeLabel,
          state: '',
          lat: coords.$1,
          lon: coords.$2,
          addedAt: DateTime.now(),
        ),
      );
    }
    setState(() => _favs = _favorites.allSync());
    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          _favorites.isFavorite(_placeLabel, '')
              ? 'Saved locally — survives offline & restarts'
              : 'Removed from favorites',
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  /// TASK-039: single-tap quick-switch via the bottom sheet; "Custom mix"
  /// opens the full multi-select onboarding flow.
  Future<void> _openPersonaPicker() async {
    final chosen = await PersonaSwitcherSheet.show(
      context,
      activeKey: _personas.isNotEmpty ? _personas.first : 'health',
      onOpenCustomMix: () => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => OnboardingScreen(
            initial: _personas,
            onDone: (selected) async {
              final next =
                  selected.isEmpty ? const ['health', 'commuter'] : selected;
              await _applyPersonaMix(next);
              if (!mounted) return;
              // Close onboarding, then the still-open persona sheet.
              Navigator.of(context)..pop()..pop();
            },
          ),
        ),
      ),
    );
    if (chosen == null) return; // sheet dismissed
    // Single-persona focus mode: the chosen persona leads the mix.
    await _applyPersonaMix(
      [chosen, ..._personas.where((p) => p != chosen)],
    );
  }

  Future<void> _applyPersonaMix(List<String> next) async {
    await widget.store.save(next);
    if (!mounted) return;
    setState(() {
      _personas = next;
      _payload = null; // triggers AnimatedSwitcher fade-through
    });
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final isFav = _favorites.isFavorite(_placeLabel, '');
    return Scaffold(
      appBar: AppBar(
        title: InkWell(
          onTap: _openSearch,
          borderRadius: BorderRadius.circular(8),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(_placeLabel),
                const SizedBox(width: 4),
                const Icon(Icons.expand_more, size: 18),
              ],
            ),
          ),
        ),
        actions: [
          IconButton(
            icon: Icon(
              isFav ? Icons.star_rounded : Icons.star_border_rounded,
              color: isFav ? Colors.amber : null,
            ),
            tooltip: 'Favorite',
            onPressed: _toggleFavorite,
          ),
          IconButton(
            icon: const Icon(Icons.tune_outlined),
            tooltip: 'Personas',
            onPressed: _openPersonaPicker,
          ),
        ],
      ),
      drawer: _FavoritesDrawer(
        favorites: _favs,
        onSelect: (f) async {
          Navigator.of(context).pop();
          await widget.store.saveLocation(f.lat, f.lon);
          await widget.store.saveLabel(f.name);
          if (!mounted) return;
          setState(() {
            _coords = (f.lat, f.lon);
            _placeLabel = f.name;
            _payload = null;
          });
          _load();
        },
        onRemove: (f) {
          _favorites.remove(f.name, f.state);
          setState(() => _favs = _favorites.allSync());
        },
      ),
      body: Column(
        children: [
          if (_conn == ConnState.offline)
            Material(
              color: Theme.of(context).colorScheme.tertiaryContainer,
              child: const SizedBox(
                width: double.infinity,
                child: Padding(
                  padding: EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.cloud_off_outlined, size: 14),
                      SizedBox(width: 6),
                      Text(
                        'Offline — cached data & full search still work',
                        style: TextStyle(fontSize: 12),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          Expanded(child: _buildBody()),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _refresh,
        child: const Icon(Icons.refresh),
      ),
    );
  }

  Widget _buildBody() {
    final payload = _payload;

    // All states live under one AnimatedSwitcher so persona switches
    // (TASK-020) fade-through: old cards → loading → new card layout.
    final Widget child;
    if (_error != null && payload == null) {
      child = KeyedSubtree(
        key: const ValueKey('error'),
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(
              'Could not load weather.\n$_error',
              textAlign: TextAlign.center,
            ),
          ),
        ),
      );
    } else if (payload == null) {
      child = const KeyedSubtree(
        key: ValueKey('loading'),
        child: Center(child: CircularProgressIndicator()),
      );
    } else {
      // Key includes the persona mix + payload identity: transitions fire on
      // persona switch or new data, stay quiet on 304-confirmed refreshes.
      child = KeyedSubtree(
        key: ValueKey('${_personas.join(',')}|${payload.hashCode}'),
        child: RefreshIndicator(
          onRefresh: _refresh,
          child: SduiHomeView(
            payload: payload,
            actions: SduiActions(onCityTap: _onCityTap),
          ),
        ),
      );
    }

    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 350),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeIn,
      transitionBuilder: (animChild, anim) => FadeTransition(
        opacity: anim,
        child: SlideTransition(
          position: Tween<Offset>(
            begin: const Offset(0, 0.02),
            end: Offset.zero,
          ).animate(anim),
          child: animChild,
        ),
      ),
      child: child,
    );
  }

  /// Multi-city carousel tap → switch the app's active location.
  Future<void> _onCityTap(CitySummary c) async {
    await widget.store.saveLocation(c.lat, c.lon);
    await widget.store.saveLabel(c.name);
    if (!mounted) return;
    setState(() {
      _coords = (c.lat, c.lon);
      _placeLabel = c.name;
      _payload = null;
    });
    _load();
  }
}

class _FavoritesDrawer extends StatelessWidget {
  final List<FavoriteLocation> favorites;
  final ValueChanged<FavoriteLocation> onSelect;
  final ValueChanged<FavoriteLocation> onRemove;

  const _FavoritesDrawer({
    required this.favorites,
    required this.onSelect,
    required this.onRemove,
  });

  @override
  Widget build(BuildContext context) {
    return Drawer(
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text('Favorites',
                  style: Theme.of(context).textTheme.titleLarge),
            ),
            if (favorites.isEmpty)
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text(
                  'Tap the star to save your current location.\n'
                  'Favorites persist offline and across restarts.',
                ),
              )
            else
              Expanded(
                child: ListView.builder(
                  itemCount: favorites.length,
                  itemBuilder: (context, i) {
                    final f = favorites[i];
                    return ListTile(
                      leading: const Icon(Icons.star_rounded, color: Colors.amber),
                      title: Text(f.name),
                      subtitle: f.state.isNotEmpty ? Text(f.state) : null,
                      trailing: IconButton(
                        icon: const Icon(Icons.delete_outline, size: 20),
                        onPressed: () => onRemove(f),
                      ),
                      onTap: () => onSelect(f),
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
