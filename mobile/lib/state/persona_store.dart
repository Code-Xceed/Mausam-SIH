import 'package:hive_ce/hive.dart';

/// Persona selection store (TASK-021). Tags persist across restarts and are
/// sent to the backend as the composer's ranking context.
class PersonaStore {
  static const _boxName = 'persona_box';
  static const _key = 'active_personas';
  static const _onboardedKey = 'is_onboarded';
  static const _locKey = 'last_location';
  static const _labelKey = 'last_location_label';
  static const _serverUrlKey = 'backend_server_url';

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
    final isOnboarded = box.get(_onboardedKey) == 'true';
    final raw = box.get(_key);
    if (!isOnboarded && (raw == null || raw.isEmpty)) return null;
    if (raw == null || raw.isEmpty) return const ['health', 'commuter'];
    final valid = raw.split(',').where((p) => allPersonas.containsKey(p)).toList();
    return valid.isEmpty ? const ['health', 'commuter'] : valid;
  }

  Future<void> save(List<String> personas) async {
    final box = await _hive;
    final valid = personas.where((p) => allPersonas.containsKey(p)).toList();
    await box.put(_key, valid.join(','));
    await box.put(_onboardedKey, 'true');
    await box.flush();
  }

  Future<void> saveLocation(double lat, double lon) async {
    final box = await _hive;
    await box.put(_locKey, '$lat,$lon');
    await box.flush();
  }

  Future<(double, double)?> loadLocation() async {
    final box = await _hive;
    final raw = box.get(_locKey);
    if (raw == null) return null;
    final parts = raw.split(',');
    if (parts.length < 2) return null;
    final lat = double.tryParse(parts[0]);
    final lon = double.tryParse(parts[1]);
    if (lat == null || lon == null) return null;
    return (lat, lon);
  }

  Future<void> saveLabel(String label) async {
    final box = await _hive;
    await box.put(_labelKey, label);
    await box.flush();
  }

  Future<String?> loadLabel() async {
    final box = await _hive;
    return box.get(_labelKey);
  }

  Future<void> saveServerUrl(String url) async {
    final box = await _hive;
    await box.put(_serverUrlKey, url.trim());
    await box.flush();
  }

  Future<String?> loadServerUrl() async {
    final box = await _hive;
    final url = box.get(_serverUrlKey);
    if (url == null || url.trim().isEmpty) return null;
    return url.trim();
  }
}
