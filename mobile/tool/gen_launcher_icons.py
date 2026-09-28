"""Generate Android launcher icons — pure Pillow, no network, no Flutter tool.

The android/ tree was hand-written and never had launcher icons; AAPT fails
with `resource mipmap/ic_launcher not found` without them. This produces:

  - Legacy full-bleed icons: mipmap-{mdpi..xxxhdpi}/ic_launcher.png (+_round)
  - Adaptive icon (API 26+): ic_launcher_foreground.png + anydpi-v26 XML,
    with the brand blue as a color background and a monochrome layer for
    Android 13 themed icons.

Usage: backend/.venv/Scripts/python mobile/tool/gen_launcher_icons.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

RES = Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main" / "res"

BRAND = (11, 87, 208, 255)  # #0B57D0 — same blue as the launch splash
WHITE = (255, 255, 255, 255)

# density -> legacy full-bleed icon size (px)
LEGACY = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
# adaptive layers use a 108dp canvas; the glyph must fit the 66dp safe zone
ADAPTIVE = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}

ADAPTIVE_XML = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@color/mausam_icon_bg" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
    <monochrome android:drawable="@mipmap/ic_launcher_foreground" />
</adaptive-icon>
"""


def draw_mark(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float) -> None:
    """Sun-behind-cloud glyph; s = half-extent of the drawable safe square."""
    # Sun (upper-left), rays first so the disc covers their inner ends.
    sun_r = 0.16 * s
    scx, scy = cx - 0.30 * s, cy - 0.32 * s
    w = max(2, int(0.05 * s))
    for i in range(8):
        a = i * math.pi / 4
        d.line(
            (
                scx + 1.30 * sun_r * math.cos(a), scy + 1.30 * sun_r * math.sin(a),
                scx + 1.75 * sun_r * math.cos(a), scy + 1.75 * sun_r * math.sin(a),
            ),
            fill=WHITE, width=w,
        )
    d.ellipse((scx - sun_r, scy - sun_r, scx + sun_r, scy + sun_r), fill=WHITE)
    # Cloud (two puffs + base slab), drawn over the sun's lower edge.
    d.ellipse((cx - 0.46 * s, cy - 0.10 * s, cx + 0.02 * s, cy + 0.42 * s), fill=WHITE)
    d.ellipse((cx - 0.10 * s, cy - 0.28 * s, cx + 0.52 * s, cy + 0.30 * s), fill=WHITE)
    d.rounded_rectangle(
        (cx - 0.44 * s, cy + 0.10 * s, cx + 0.48 * s, cy + 0.42 * s),
        radius=0.16 * s, fill=WHITE,
    )


def legacy_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), BRAND)
    draw_mark(ImageDraw.Draw(img), size / 2, size / 2, size / 2)
    return img


def adaptive_foreground(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # Scale glyph into the 66/108 safe zone so no mask ever clips it.
    draw_mark(ImageDraw.Draw(img), size / 2, size / 2, size * (66 / 108) / 2)
    return img


def main() -> None:
    for dens, px in LEGACY.items():
        folder = RES / f"mipmap-{dens}"
        folder.mkdir(parents=True, exist_ok=True)
        legacy_icon(px).save(folder / "ic_launcher.png")
        legacy_icon(px).save(folder / "ic_launcher_round.png")
        adaptive_foreground(ADAPTIVE[dens]).save(folder / "ic_launcher_foreground.png")

    anydpi = RES / "mipmap-anydpi-v26"
    anydpi.mkdir(parents=True, exist_ok=True)
    (anydpi / "ic_launcher.xml").write_text(ADAPTIVE_XML, encoding="utf-8")
    (anydpi / "ic_launcher_round.xml").write_text(ADAPTIVE_XML, encoding="utf-8")

    print(f"Launcher icons written under {RES}")


if __name__ == "__main__":
    main()
