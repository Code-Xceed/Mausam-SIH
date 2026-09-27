import 'package:flutter/material.dart';

import 'language_store.dart';

/// TASK-063: frictionless language picker. One tap switches the UI language;
/// the choice persists and the app re-renders instantly (no restart).
class LanguageSheet {
  LanguageSheet._();

  static Future<String?> show(BuildContext context, String current) async {
    return showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (sheetCtx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Row(
                children: [
                  const Icon(Icons.translate, size: 20),
                  const SizedBox(width: 8),
                  Text('Choose language / भाषा चुनें',
                      style: Theme.of(sheetCtx).textTheme.titleMedium),
                ],
              ),
            ),
            for (final entry in LanguageStore.supported.entries)
              ListTile(
                title: Text(entry.value),
                trailing:
                    entry.key == current ? const Icon(Icons.check_rounded) : null,
                onTap: () => Navigator.of(sheetCtx).pop(entry.key),
              ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }
}
