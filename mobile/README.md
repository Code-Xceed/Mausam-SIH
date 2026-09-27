# mobile/ — Flutter Client (Android-first per AD-002)

Phase 0 ships a boot-verified shell only. Generate the platform wrappers
locally (they are machine-specific and not committed):

```bash
flutter create --platforms=android --org in.sih .   # run inside mobile/
flutter pub get
flutter run                                          # with backend on :8000
```

The shell pings `GET /health` on the gateway (emulator default
`http://10.0.2.2:8000`; override with `--dart-define=BACKEND_URL=...`).

Phase roadmap: SDUI registry + error boundaries (Phase 2), debounced
search + Hive favorites (Phase 3), 8 persona widgets (Phase 4), Algorithm
Inspector (Phase 5), disaster hijack (Phase 6).
