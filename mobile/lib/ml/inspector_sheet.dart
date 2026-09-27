import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../sdui/sdui_models.dart';

/// TASK-045: the live "Algorithm Inspector" — a developer bottom-sheet that
/// shows, in real time:
///   • the context vector x_t of the LAST bandit-ranked request,
///   • per-arm exploitation (θ·x), exploration bonus, and UCB score,
///   • warm-start priors and the A/B engine in use.
///
/// Data source: the backend's /v1/debug/bandit/* endpoints (same data the
/// SDUI payload's `personas.bandit` block carries). Interacting with widgets
/// then re-opening the sheet shows live weight shifts — the jury sees the
/// bandit LEARN.
class InspectorSheet {
  InspectorSheet._();

  static Future<void> show(BuildContext context, {required String baseUrl}) async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (_) => _InspectorBody(baseUrl: baseUrl),
    );
  }
}

class _InspectorBody extends StatefulWidget {
  final String baseUrl;
  const _InspectorBody({required this.baseUrl});

  @override
  State<_InspectorBody> createState() => _InspectorBodyState();
}

class _InspectorBodyState extends State<_InspectorBody> {
  final _client = http.Client();
  Map<String, dynamic>? _last;
  Map<String, dynamic>? _stats;
  String? _error;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _refresh();
    // Live view: poll while open so weight shifts appear without manual
    // refresh after each widget interaction.
    _timer = Timer.periodic(const Duration(seconds: 3), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _client.close();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final last = await _client
          .get(Uri.parse('${widget.baseUrl}/v1/debug/bandit/last'))
          .timeout(const Duration(seconds: 3));
      final stats = await _client
          .get(Uri.parse('${widget.baseUrl}/v1/debug/bandit/stats'))
          .timeout(const Duration(seconds: 3));
      if (!mounted) return;
      setState(() {
        _last = jsonDecode(last.body) as Map<String, dynamic>;
        _stats = jsonDecode(stats.body) as Map<String, dynamic>;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SafeArea(
      child: Container(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.85,
        ),
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        child: _error != null && _last == null
            ? Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('Inspector offline', style: theme.textTheme.titleLarge),
                  const SizedBox(height: 8),
                  Text('Backend unreachable: $_error'),
                ],
              )
            : ListView(
                shrinkWrap: true,
                children: [
                  Text('Algorithm Inspector — LinUCB live',
                      style: theme.textTheme.titleLarge),
                  if (_last == null || _last!['available'] != true) ...[
                    const SizedBox(height: 8),
                    const Text(
                      'No bandit-ranked request yet. Open the persona sheet, '
                      'switch engine to "bandit", interact with a card, then '
                      'reopen this sheet to see live weight shifts.',
                    ),
                  ] else ...[
                    const SizedBox(height: 12),
                    _ContextVectorBlock(x: (_last!['x'] as List).cast<num>()),
                    const SizedBox(height: 16),
                    Text('Per-arm UCB scores', style: theme.textTheme.titleSmall),
                    const SizedBox(height: 6),
                    for (final s in (_last!['scores'] as List).cast<Map<String, dynamic>>())
                      _ArmScoreRow(score: s),
                    const SizedBox(height: 12),
                    _StatsBlock(stats: _stats),
                  ],
                  const SizedBox(height: 8),
                  Text(
                    'reward = click +1.0 · dismiss −1.0 · dwell ≥ 3s +0.3',
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
      ),
    );
  }
}

class _ContextVectorBlock extends StatelessWidget {
  final List<num> x;
  const _ContextVectorBlock({required this.x});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('context vector x_t (dim ${x.length})',
              style: theme.textTheme.labelLarge),
          const SizedBox(height: 6),
          Text(
            x.map((v) => v.toStringAsFixed(2)).join('  '),
            style: theme.textTheme.bodySmall?.copyWith(
              fontFamily: 'monospace',
              fontSize: 10,
            ),
          ),
        ],
      ),
    );
  }
}

class _ArmScoreRow extends StatelessWidget {
  final Map<String, dynamic> score;
  const _ArmScoreRow({required this.score});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final exploit = (score['exploitation'] as num?)?.toDouble() ?? 0;
    final explore = (score['exploration'] as num?)?.toDouble() ?? 0;
    final ucb = (score['ucb'] as num?)?.toDouble() ?? 0;
    final maxAbs = (exploit.abs() + explore.abs() + 0.001);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          SizedBox(
            width: 150,
            child: Text(score['arm'].toString(),
                style: theme.textTheme.bodySmall),
          ),
          Expanded(
            child: Stack(
              children: [
                Container(height: 14, color: theme.dividerColor.withValues(alpha: 0.3)),
                FractionallySizedBox(
                  widthFactor: (exploit.abs() / maxAbs).clamp(0, 1),
                  child: Container(height: 14, color: theme.colorScheme.primary),
                ),
                FractionallySizedBox(
                  widthFactor: (explore.abs() / maxAbs).clamp(0, 1),
                  child: Container(
                    height: 14,
                    width: MediaQuery.of(context).size.width *
                        (explore.abs() / maxAbs).clamp(0, 1),
                    color: theme.colorScheme.tertiary.withValues(alpha: 0.6),
                  ),
                ),
              ],
            ),
          ),
          SizedBox(
            width: 52,
            child: Text(ucb.toStringAsFixed(3),
                textAlign: TextAlign.end,
                style: theme.textTheme.bodySmall
                    ?.copyWith(fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }
}

class _StatsBlock extends StatelessWidget {
  final Map<String, dynamic>? stats;
  const _StatsBlock({this.stats});

  @override
  Widget build(BuildContext context) {
    if (stats == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final warm = stats!['warm_start'] as Map<String, dynamic>?;
    final totalImpressions = (stats!['arms'] as List?)
        ?.cast<Map<String, dynamic>>()
        .fold<int>(0, (sum, a) => sum + ((a['impressions'] as num?)?.toInt() ?? 0));
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('model state', style: theme.textTheme.labelLarge),
          const SizedBox(height: 4),
          Text('total impressions seen: ${totalImpressions ?? '?'}'),
          Text('warm-start prior (disaster card): '
              '${(warm?['priors'] as Map<String, dynamic>?)?['disaster_lifeline_card']}'),
          Text('ridge λ: ${stats!['ridge']} · α: ${stats!['alpha']}'),
        ],
      ),
    );
  }
}
