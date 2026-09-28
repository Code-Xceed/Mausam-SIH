# Backup Deployment — Offline Host & Device Prep (TASK-075)

> Acceptance: 100% demo self-sufficiency — no venue internet, no venue power
> dependence, two independent physical phones pre-installed.

## 1. Release APK (TASK-077 build)

```bash
cd mobile
flutter build apk --release --split-per-abi --dart-define=BACKEND_URL=http://192.168.43.1:8000
# outputs:
#   build/app/outputs/flutter-apk/app-arm64-v8a-release.apk   (flagship phones)
#   build/app/outputs/flutter-apk/app-armeabi-v7a-release.apk (budget phone)
```

- R8 minify + resource shrink are already on (`android/app/build.gradle`).
- Realistic size: **~26 MB (armv7) / ~31 MB (arm64)** per ABI — the official
  maplibre_gl plugin's native `libmaplibre.so` (~11 MB) + `libflutter.so` dominate;
  the original <18 MB target predates the map integration. Verify:
  `ls -lh build/app/outputs/flutter-apk/`.
- The `BACKEND_URL` dart-define must point at the laptop's hotspot IP.
- Local build prerequisites (Windows): JDK 21 (maplibre 0.27 Java sources),
  Android cmdline-tools + NDK 28.2.13676358 + platforms 34/35/36. A detached
  launcher is provided: run `mobile\build_apk_release.bat`, monitor `apk_build.log`.

## 2. Offline host laptop

```bash
# One-time
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt

# Demo day
# 1. Windows: Settings → Mobile hotspot ON (or a travel router, preferred)
# 2. Find laptop IP on the hotspot subnet (usually 192.168.43.1)
# 3. Boot with SEED mode so ZERO upstream calls happen:
API_MODE=SEED .venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# 4. Smoke: from a phone browser hit http://192.168.43.1:8000/health
```

- The app works even if the phones can't reach the laptop: SDUI cache +
  bundled fallback layout render from Hive (airplane-mode cold boot is a
  scripted part of the demo).
- Charge: laptop + 20 000 mAh power bank + 2 USB-C cables. Hotspot + server
  on battery draws ~15 W → 3+ hours.

## 3. Phone prep (both devices)

1. Install the APK; open once; grant notification + coarse location.
2. Long-press city name → "Stage demo Red Alert" → verify takeover →
   "I am safe" → verify feed returns.
3. Settings: font size default, brightness ~70%, auto-rotate OFF,
   Do-not-disturb OFF (disaster channel must break through).
4. Battery: full + battery-saver exceptions for Mausam (background alerts).
5. Airplane mode test: cold boot < 750 ms, search works, map overlays render
   from the offline tile cache, checklists open.
6. Home-screen widget placed (2x2) — verify red flip after staging a drill.

## 4. Final checklist (print this)

- [ ] 2 phones: APK `arm64` + `armv7`, widget placed, drills rehearsed
- [ ] Laptop: venv + fixtures verified, hotspot tested, battery 100%
- [ ] Power bank + cables + phone stands
- [ ] This repo at the demo commit: `git log --oneline -1`
- [ ] `docs/evidence/*.json` regenerated the morning of the event:
      `cd backend && python -m pytest tests/test_phase9.py -q`
