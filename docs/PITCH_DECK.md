# Mausam Next-Gen — 10-Slide SIH Master Pitch Deck (TASK-073)

> Companion to docs/PITCH.md. Each slide = one message + one visual + the
> number that wins the point. Rehearsal timing lives in docs/DEMO_SCRIPT.md.

---

**Slide 1 — The Crisis (Shock)**
"India's official weather app scores **2.8 stars** — 10 crore users, one
generic feed. A farmer, a fisherman, an asthmatic in Delhi and a parent
getting kids to school see THE SAME screen. During Cyclone Biparjoy,
warnings arrived as a wall of text nobody read."
*Visual: 1-star reviews wall + a single generic app screenshot.*

**Slide 2 — The Insight**
"Weather isn't one problem. It's eight audiences with eight different
lifelines. Personalization isn't a luxury feature here — it's whether the
right warning reaches the right person in time."
*Visual: the 8 persona icons fanning out from one cloud.*

**Slide 3 — The Platform**
"Server-Driven UI: the backend doesn't send data, it sends DECISIONS — a
composed, ranked, personalized screen in under 15 KB. One JSON contract,
zero app-store delays, A/B from day one."
*Visual: architecture diagram — IMD/CPCB/INCOIS/NDMA → gateway → SDUI.*

**Slide 4 — Sovereign Data Federation**
"Every source is Indian: IMD forecasts, CPCB air quality, INCOIS ocean
state, MOSDAC satellites, GKMS agromet, NDMA SACHET alerts. A circuit
breaker with fixture replay means the demo works even if the venue Wi-Fi
dies — national infrastructure that can't fail on stage."
*Visual: 6 source logos → one pipeline, "1200ms breaker" badge.*

**Slide 5 — The Learning Engine (LinUCB)**
"A context-aware bandit re-ranks every card for every user, every request.
Offline replay against logged traffic: **+89.9% cumulative reward vs random
ordering, +87.4% vs ε-greedy** — while safety pins stay rule-based. Rules
decide IF a card pins; ML only orders the rest."
*Visual: ml/replay_results.png learning curve.*

**Slide 6 — The Lifeline Mode**
"When an NDMA Red alert polygon touches your 5 km cell, the phone TAKES
OVER: full-screen evacuation corridors, shelter markers, offline SOS —
pushed in under 2.5 s, waking through Doze. 58 NDMA safety steps bundled
in the binary, readable in airplane mode."
*Visual: lifeline takeover screenshot + the 2.5 s / 5 km numbers.*

**Slide 7 — Language & Inclusion**
"Hindi, Tamil, Bengali, Telugu, Marathi — glossary-driven offline
translation with live Bhashini pass-through. 'Suno Mausam' speaks the
advisory aloud. Large-text and high-contrast modes for elderly users;
glyphs that need no literacy at all."
*Visual: language selector + TTS FAB screenshots.*

**Slide 8 — Privacy by Design (DPDP 2023)**
"Coarse 5 km snap before transmit — raw GPS never leaves the device. One
tap wipes every server-side trace. Favorites live on-device, encrypted."
*Visual: GPS→grid diagram + 'Clear My Footprint' button.*

**Slide 9 — Engineering Discipline**
"217 backend tests green in CI · SDUI payload ≤ 15 KB (10× smaller than
industry median) · <60 KB map tiles · 5-min session < 1.2 MB · contract
validated on every commit."
*Visual: CI badge + evidence JSONs from docs/evidence/.*

**Slide 10 — The Ask**
"Mausam Next-Gen is ready for MeitY/MoES pilot: the platform personalizes
for every citizen and takes over the screen when it matters most — during
a disaster. Demo: 7 minutes, fully offline, on two physical phones."
*Visual: the two phones running the choreographed demo.*

---

### Speaker notes (per-slide one-liners)
1. Slow down on "2.8 stars" — let it land.
2. Point at a jury member's persona: "You would see a different home."
3. "The server decides, the client renders — that's the whole trick."
4. "Venue Wi-Fi dies? Nothing breaks. Watch."
5. "+89.9% is replay-proven, not hand-waved. The chart is generated in CI."
6. Stage the Red Alert live here (long-press city name) — phones hijack.
7. Tap the TTS button; switch to Tamil and back.
8. "No raw GPS. Ever."
9. "Numbers are in the repo: docs/evidence/."
10. Close: "Warnings that reach the right person, in their language, in time."
