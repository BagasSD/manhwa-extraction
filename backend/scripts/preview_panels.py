"""
Preview panel auto-detection (docs/plan-fitur-panel-crop.md, phase 1).

Draws the detected panel boxes and their reading-order numbers on each page
and saves `<page>.panels.png`, so detection accuracy can be checked by eye
before trusting it in the review UI. Runs locally; no model, no tokens.

Usage (from backend/):
    python scripts/preview_panels.py ../data/chapters/chapter-1
    python scripts/preview_panels.py page-005.webp --out ../data/panel-previews
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.services.chapter_service import SUPPORTED_IMAGE_EXTENSIONS, natural_sort_key  # noqa: E402
from app.services.panel_service import detect_panels  # noqa: E402

COLORS = [(255, 64, 64), (64, 200, 64), (64, 128, 255), (255, 180, 0), (220, 64, 220), (0, 200, 200)]


def annotate(path: Path) -> tuple[Image.Image, int]:
    image = Image.open(path).convert("RGB")
    panels = detect_panels(image)
    draw = ImageDraw.Draw(image)
    stroke = max(3, image.width // 150)
    font = ImageFont.load_default(size=max(24, image.width // 16))
    for panel in panels:
        ymin, xmin, ymax, xmax = panel.bbox
        color = COLORS[(panel.panel_index - 1) % len(COLORS)]
        draw.rectangle([xmin, ymin, xmax - 1, ymax - 1], outline=color, width=stroke)
        draw.text((xmin + stroke * 2, ymin + stroke), str(panel.panel_index), fill=color, font=font,
                  stroke_width=3, stroke_fill=(0, 0, 0))
    return image, len(panels)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="Page image or folder of page images")
    parser.add_argument("--out", type=Path, help="Output folder (default: next to the images, in panel-preview/)")
    args = parser.parse_args()

    if args.source.is_dir():
        pages = sorted(
            (p for p in args.source.iterdir() if p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS),
            key=lambda p: natural_sort_key(p.name),
        )
        out_dir = args.out or args.source / "panel-preview"
    else:
        pages = [args.source]
        out_dir = args.out or args.source.parent / "panel-preview"
    out_dir.mkdir(parents=True, exist_ok=True)

    for page in pages:
        annotated, count = annotate(page)
        out_path = out_dir / f"{page.stem}.panels.png"
        annotated.save(out_path)
        print(f"{page.name}: {count} panel(s) -> {out_path}")


if __name__ == "__main__":
    main()
