# 7-Minute Live Demonstration — Choreography (TASK-074)

> Goal: 6:45 completion, leaving 15 s buffer + jury Q&A. Two phones + one
> laptop hotspot. Every beat has a fallback (the demo CANNOT die).

## Pre-flight (before jury walks in — NOT in the 7 minutes)
- [ ] Laptop: `cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000`
      (or `docker compose up`); verify `GET /health` → 200.
- [ ] Phone A (hero) + Phone B (jury-roam): APK installed, airplane mode ON,
      open app once → cold boot from Hive cache (<750 ms), search "Mumbai".
- [ ] Airplane mode OFF on Phone A; hotspot from laptop connected.
- [ ] `docs/evidence/` open in a browser tab (slide 9 backup).
- [ ] Kill any stale `demo-inject` alerts: `DELETE /v1/admin/alerts/injected`.

## The 7 minutes

**0:00–1:00 — Hook (Slide 1-2)**
"Ten crore users, one generic screen, 2.8 stars." Open Phone A: Mausam home
loads instantly from cache. Switch persona: tap tune icon → "Beachgoer" —
*tide card rises without restart* (TASK-039).

**1:00–2:30 — Sovereign pipeline (Slide 3-4)**
Show `/health` on the laptop: sources NDMA_CAP, IMD, CPCB, INCOIS.
**Kill the laptop's upstream Wi-Fi now** (unplug ethernet / disable Wi-Fi
upstream, keep hotspot). Refresh Phone A — everything still renders (SEED
replay). "The breaker fell back to authentic fixtures. Nothing broke."

**2:30–3:30 — Personalization (Slide 5)**
Drawer → "Algorithm Inspector": live x_t, arm scores. Click a card, dismiss
another, reopen inspector — **scores moved**. Show `ml/replay_results.json`:
+89.9% vs random. "This is measured, not claimed."

**3:30–5:00 — THE DISASTER (Slide 6) — the money beat**
Long-press "Mumbai" on Phone A → "SIMULATED DRILL staged — Lifeline Mode
engaged." **Phone A hijacks**: red takeover, evacuation corridor, shelters.
Tap SOS → clipboard. Open checklists → cyclone tab, scroll — "58 NDMA steps,
offline in the binary." Put Phone A **face-down, screen locked**; stage the
drill again from admin API (`POST /v1/admin/inject-alert`, city=mumbai) →
"Even asleep, the push wakes it — priority HIGH, Doze-expedited worker."
Phone A audibly alerts within seconds.

**5:00–5:45 — Inclusion (Slide 7)**
Phone B (still airplane mode): language → हिन्दी — instant re-render from
the cached bundle. Tap the volume FAB — "Suno Mausam" speaks the advisory
in Hindi, synthesized on-device. Large-text toggle in the drawer — whole UI
scales.

**5:45–6:30 — Map + Privacy (Slide 8)**
Phone B: map icon → hazard map renders CAP polygon + boundaries from the
offline tile ring-buffer ("downloaded nothing — it's cached"). Tap "Locate
me" → footer shows "sharing cell 19.05_72.85 only — raw GPS never leaves."
Drawer → "Clear My Footprint" on the laptop API: `POST /v1/privacy/purge`
→ server trace erased.

**6:30–6:45 — Close (Slide 10)**
"Warnings that reach the right person, in their language, in time — and
when it matters most, the phone takes over. Two phones, zero venue
internet, fully reproducible in the repo."

## Fallback matrix
| Failure | Fallback |
|---|---|
| Laptop dies | Phone A runs fully offline (cache + bundled fallback layout) |
| Push/Doze fails on stage | Already-staged long-press drill (worked at 3:30) |
| TTS voice pack missing | English fallback voice; slide 7 screenshot |
| Map tiles missing | Lifeline screen's schematic corridor map (same story) |
| Wi-Fi totally dead at venue | Whole script runs on laptop hotspot / airplane mode |

## Rehearsal checklist (5 dry-runs before the event)
- [ ] Full run ≤ 6:45 twice in a row
- [ ] Both backup phones flashed with the release APK (TASK-075)
- [ ] Offline host laptop verified on battery only
- [ ] `git rev-parse HEAD` of the demo commit noted on the pitch laptop
