import 'dart:async';

import 'package:flutter/material.dart';

import '../search/gazetteer.dart';
import '../search/search_service.dart';

/// Location search screen (TASK-024/025/026 demo surface).
/// Zero network, 500ms debounce, typo-tolerant, race-free via switchMap.
class SearchScreen extends StatefulWidget {
  final ValueChanged<Town> onTownSelected;

  const SearchScreen({super.key, required this.onTownSelected});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _controller = TextEditingController();
  final _focus = FocusNode();
  late final SearchService _search;
  StreamSubscription? _sub;
  SearchResult _result = const SearchResult(query: '', towns: [], loading: false);

  @override
  void initState() {
    super.initState();
    _search = SearchService();
    _search.start();
    _sub = _search.results.listen((r) {
      if (mounted) setState(() => _result = r);
    });
    _focus.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    _sub?.cancel();
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Search location'),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            child: TextField(
              controller: _controller,
              focusNode: _focus,
              autofocus: true,
              decoration: InputDecoration(
                hintText: 'Town, city or district… works offline',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _result.loading
                    ? const Padding(
                        padding: EdgeInsets.all(12),
                        child: SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      )
                    : (_controller.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear),
                            onPressed: () {
                              _controller.clear();
                              _search.submit('');
                              setState(() {});
                            },
                          )
                        : null),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
              ),
              onChanged: (q) {
                _search.submit(q);
                setState(() {});
              },
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: [
                Icon(Icons.cloud_off_outlined,
                    size: 14, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: 6),
                Text(
                  'On-device gazetteer · ${Gazetteer.instance.townCount} towns · no network used',
                  style: theme.textTheme.labelSmall
                      ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
          const SizedBox(height: 4),
          Expanded(
            child: _result.towns.isEmpty && _result.query.isNotEmpty && !_result.loading
                ? Center(
                    child: Text(
                      'No match for “${_result.query}”',
                      style: theme.textTheme.bodyMedium,
                    ),
                  )
                : ListView.builder(
                    itemCount: _result.towns.length,
                    itemBuilder: (context, i) {
                      final t = _result.towns[i];
                      return ListTile(
                        leading: const Icon(Icons.location_on_outlined),
                        title: Text(t.name),
                        subtitle: Text(t.subtitle),
                        trailing: t.population != null
                            ? Text(
                                _compact(t.population!),
                                style: theme.textTheme.labelSmall,
                              )
                            : null,
                        onTap: () => widget.onTownSelected(t),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  String _compact(int n) {
    if (n >= 10000000) return '${(n / 10000000).toStringAsFixed(1)}Cr';
    if (n >= 100000) return '${(n / 100000).toStringAsFixed(1)}L';
    if (n >= 1000) return '${(n / 1000).toStringAsFixed(0)}K';
    return '$n';
  }
}
