#!/usr/bin/env python
"""Generate the Hyperion brand assets from the source logo.

The source artwork lives in ``assets/brand/hyperion-logo.png`` (a wide lockup:
emblem on the left, "HYPERION" wordmark on the right) and is the single source
of truth. This script derives everything the app actually serves, into
``public/``:

    hyperion-logo.png        full lockup, ink artwork   (light surfaces)
    hyperion-logo-light.png  full lockup, paper artwork  (dark surfaces)
    hyperion-mark.png        emblem only, square pad, transparent
    hyperion-mark-light.png  emblem only, paper, for dark surfaces
    hyperion-favicon.png     512px icon: ink tile + paper emblem
    apple-touch-icon.png     180px icon, same treatment
    favicon.svg              the emblem embedded as a base64 PNG

Re-run it after replacing the source artwork:

    .venv/Scripts/python scripts/build_brand_assets.py      # Windows
    .venv/bin/python scripts/build_brand_assets.py          # macOS / Linux

Requires Pillow (a build-time tool only; it is not needed to run the app).
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "brand" / "hyperion-logo.png"
OUT = ROOT / "public"

INK = (18, 18, 18, 255)  # --ink
PAPER = (247, 241, 223, 255)  # --paper

# In the source lockup the emblem ends before this column and the wordmark
# begins after it; verified by scanning the alpha channel.
EMBLEM_RIGHT_EDGE = 660


def trim(image: Image.Image) -> Image.Image:
    """Crop away fully transparent margins."""
    box = image.getbbox()
    return image.crop(box) if box else image


def recolor(image: Image.Image, color: tuple[int, int, int, int]) -> Image.Image:
    """Replace RGB with a flat colour, preserving the alpha silhouette."""
    flat = Image.new("RGBA", image.size, color)
    flat.putalpha(image.getchannel("A"))
    return flat


def square(image: Image.Image, size: int, fill_ratio: float = 0.92) -> Image.Image:
    """Center the artwork on a transparent square canvas."""
    target = int(size * fill_ratio)
    scaled = image.copy()
    scaled.thumbnail((target, target), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(scaled, ((size - scaled.width) // 2, (size - scaled.height) // 2), scaled)
    return canvas


def tile(mark: Image.Image, size: int) -> Image.Image:
    """A rounded ink tile with the emblem centered in paper colour."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.14), fill=INK)
    inner = square(mark, size, fill_ratio=0.66)
    canvas.alpha_composite(inner)
    return canvas


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"Source logo not found: {SOURCE}")

    OUT.mkdir(parents=True, exist_ok=True)
    source = Image.open(SOURCE).convert("RGBA")

    # 1. The full lockup, trimmed, in both finishes.
    lockup = trim(source)
    lockup.save(OUT / "hyperion-logo.png")
    lockup_light = recolor(lockup, PAPER)
    lockup_light.save(OUT / "hyperion-logo-light.png")

    # 2. The emblem on its own, square-padded so it never distorts.
    emblem_region = source.crop((0, 0, EMBLEM_RIGHT_EDGE, source.height))
    emblem = trim(emblem_region)
    mark = square(emblem, 512)
    mark.save(OUT / "hyperion-mark.png")
    mark_light = recolor(mark, PAPER)
    mark_light.save(OUT / "hyperion-mark-light.png")

    # 3. Icons: a solid tile so the mark stays visible on both light and dark
    #    browser chrome.
    favicon = tile(recolor(mark, PAPER), 512)
    favicon.save(OUT / "hyperion-favicon.png")
    favicon.resize((180, 180), Image.LANCZOS).save(OUT / "apple-touch-icon.png")

    # 4. An SVG favicon with the emblem embedded, so it stays crisp at any size.
    small = io.BytesIO()
    tile(recolor(mark, PAPER), 128).save(small, format="PNG", optimize=True)
    encoded = base64.b64encode(small.getvalue()).decode("ascii")
    (OUT / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'viewBox="0 0 128 128" role="img" aria-label="Hyperion">\n'
        f'  <image width="128" height="128" xlink:href="data:image/png;base64,{encoded}" />\n'
        "</svg>\n",
        encoding="utf-8",
    )

    for name in (
        "hyperion-logo.png",
        "hyperion-logo-light.png",
        "hyperion-mark.png",
        "hyperion-mark-light.png",
        "hyperion-favicon.png",
        "apple-touch-icon.png",
        "favicon.svg",
    ):
        path = OUT / name
        print(f"  wrote {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")

    print(f"\nlockup {lockup.width}x{lockup.height}  emblem {emblem.width}x{emblem.height}")


if __name__ == "__main__":
    main()
