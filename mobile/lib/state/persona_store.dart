import 'package:hive_ce/hive.dart';

/// Persona selection store (TASK-021). Tags persist across restarts and are
/// sent to the backend as the composer's ranking context.
class PersonaStore {
  static const _boxName = 'persona_box';
  static const _key = 'active_personas';
  static const _locKey = 'last_location';
  static const _labelKey = 'last_location_label';

  static const allPersonas = <String, String>{
    'health': 'Health-conscious',
    'fitness': 'Outdoor fitness',
    'coastal': 'Beachgoer & surfer',
    'travel': 'Traveler',
    'family': 'Parent & family',
    'farmer': 'Farmer & gardener',
    'commuter': 'Daily commuter',
    'planner': 'Event planner',
  };

  Box<String>? _box;

  Future<Box<String>> get _hive async {
    _box ??= await Hive.openBox<String>(_boxName);
    return _box!;
  }

  Future<List<String>> load() async {
    final box = await _hive;
    final raw = box.get(_key);
    if (raw == null || raw.isEmpty) return const ['health', 'commuter'];
    return raw.split(',').where((p) => allPersonas.containsKey(p)).toList();
  }

  /// Returns personas only if the user explicitly saved them at least once —
  /// distinguishes "first launch" from "defaults in use".
  Future<List<String>?> loadExplicit() async {
    final box = await _hive;
    final raw = box.get(_key);
    if (raw == null || raw.isEmpty) return null;
    final valid = raw.split(',').where((p) => allPersonas.containsKey(p)).toList();
    return valid.isEmpty ? null : valid;
  }

  Future<void> save(List<String> personas) async {
    final box = await _hive;
    final valid = personas.where((p) => allPersonas.containsKey(p)).toList();
    await box.put(_key, valid.join(','));
  }

  Future<void> saveLocation(double lat, double lon) async {
    final box = await _hive;
    await box.put(_locKey, '$lat,$lon');
  }

  Future<(double, double)?> loadLocation() async {
    final box = await _hive;
    final raw = box.get(_locKey);
    if (raw == null) return null;
    final parts = raw.split(',');
    final lat = double.tryParse(parts[0]);
    final lon = double.tryParse(parts[1]);
    if (lat == null || lon == null) return null;
    return (lat, lon);
  }

  Future<void> saveLabel(String label) async {
    final box = await _hive;
    await box.put(_labelKey, label);
  }

  Future<String?> loadLabel() async {
    final box = await _hive;
    return box.get(_labelKey);
  }
}
