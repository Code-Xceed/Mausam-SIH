"""Build the on-device Indian gazetteer asset from GeoNames data (CC BY 4.0).

Inputs (download manually — GeoNames asks for bulk downloads, not scraping):
    http://download.geonames.org/export/zip/IN.zip        (postal codes)
    https://download.geonames.org/export/dump/cities500.zip (cities w/ population)

Output: mobile/assets/gazetteer/in_towns.jsonl.gz — one JSON object per line:
    {"n": name, "s": state, "d": district, "lat": float, "lon": float, "p": population|null}

Dedup strategy: cities (population-ranked) first; postal entries are added
only when their (name, state) pair is new — so every well-known town keeps
its population ranking, and villages/PIN-localities extend coverage.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

CITIES_SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/cities500.txt")
POSTAL_SRC = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/IN.txt")
OUT_PATH = (
    Path(sys.argv[3])
    if len(sys.argv) > 3
    else Path(__file__).resolve().parents[2] / "mobile/assets/gazetteer/in_towns.jsonl.gz"
)

MAX_POSTAL_ENTRIES = 12000  # keeps asset well under budget


def main() -> None:
    if not CITIES_SRC.exists() or not POSTAL_SRC.exists():
        print("Download both GeoNames sources first (see module docstring).")
        sys.exit(1)

    seen: set[tuple[str, str]] = set()
    lines: list[str] = []

    # 1. Cities, largest population first (GeoNames cities500 is unsorted).
    cities = []
    with CITIES_SRC.open(encoding="utf-8") as f:
        for row in f:
            c = row.rstrip("\n").split("\t")
            if len(c) < 15 or c[8] != "IN":
                continue
            try:
                pop = int(c[14]) if c[14] else 0
                lat, lon = float(c[4]), float(c[5])
            except ValueError:
                continue
            cities.append((pop, c[2], c[10], lat, lon))  # pop, name, state, lat, lon

    cities.sort(reverse=True)
    for pop, name, state, lat, lon in cities:
        key = (name.casefold(), state.casefold())
        if key in seen or not name:
            continue
        seen.add(key)
        lines.append(
            json.dumps(
                {"n": name, "s": state, "d": None, "lat": round(lat, 3), "lon": round(lon, 3), "p": pop},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
    n_cities = len(lines)

    # 2. Postal localities — dedupe on (name, state) + coarse location.
    added = 0
    with POSTAL_SRC.open(encoding="utf-8") as f:
        for row in f:
            if added >= MAX_POSTAL_ENTRIES:
                break
            c = row.rstrip("\n").split("\t")
            if len(c) < 11 or c[0] != "IN" or not c[2]:
                continue
            name, state, district = c[2], c[3], c[5]
            try:
                lat, lon = float(c[9]), float(c[10])
            except ValueError:
                continue
            key = (name.casefold(), state.casefold())
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                json.dumps(
                    {"n": name, "s": state, "d": district or None, "lat": round(lat, 3), "lon": round(lon, 3), "p": None},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            added += 1

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT_PATH, "wt", encoding="utf-8", compresslevel=9) as gz:
        gz.write("\n".join(lines) + "\n")

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"cities: {n_cities}, postal additions: {added}, total: {len(lines)}")
    print(f"asset: {OUT_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
