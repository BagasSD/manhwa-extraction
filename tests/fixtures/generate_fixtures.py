"""
Script to generate synthetic fixture images for benchmarking tests.

Creates simple PIL images in tests/fixtures/ subdirectories matching
the fixture dataset structure from PRD §14.1.

Run from the project root:
    python tests/fixtures/generate_fixtures.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FIXTURE_ROOT = Path(__file__).resolve().parent

CATEGORIES = {
    "clean": [
        ("page-001.png", "Clean page — clear speech bubble", (240, 240, 255)),
        ("page-002.png", "Clean page — narration box", (240, 255, 240)),
    ],
    "difficult": [
        ("page-001.png", "Difficult — low contrast", (180, 180, 180)),
        ("page-002.png", "Difficult — busy background", (50, 70, 120)),
    ],
    "small_text": [
        ("page-001.png", "Small text panel", (255, 250, 230)),
    ],
    "text_over_art": [
        ("page-001.png", "Text over detailed art", (100, 80, 60)),
    ],
    "multiple_characters": [
        ("page-001.png", "Multiple characters scene", (230, 240, 250)),
        ("page-002.png", "Group shot", (220, 235, 245)),
    ],
    "no_dialogue": [
        ("page-001.png", "No dialogue — action panel", (200, 220, 200)),
    ],
    "sfx": [
        ("page-001.png", "SFX-heavy page", (255, 235, 200)),
    ],
}

IMAGE_SIZE = (400, 600)


def _draw_page(path: Path, label: str, bg_color: tuple[int, int, int]) -> None:
    """Create a simple synthetic manhwa-like page image."""
    img = Image.new("RGB", IMAGE_SIZE, color=bg_color)
    draw = ImageDraw.Draw(img)

    # Panel border
    draw.rectangle([10, 10, IMAGE_SIZE[0] - 10, IMAGE_SIZE[1] - 10], outline=(0, 0, 0), width=3)

    # Mock speech bubble (ellipse)
    bubble_box = [60, 40, 340, 130]
    draw.ellipse(bubble_box, fill=(255, 255, 255), outline=(0, 0, 0), width=2)

    # Text in bubble
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 10)
    except OSError:
        font = ImageFont.load_default()
        small_font = font

    draw.text((90, 65), "Don't leave!", fill=(0, 0, 0), font=font)

    # Mock character silhouette
    draw.ellipse([150, 150, 250, 230], fill=(80, 60, 40), outline=(0, 0, 0), width=2)  # head
    draw.rectangle([140, 230, 260, 380], fill=(80, 60, 40), outline=(0, 0, 0), width=2)  # body

    # Label at bottom
    draw.text((20, IMAGE_SIZE[1] - 30), label[:50], fill=(60, 60, 60), font=small_font)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG")


def main() -> None:
    created = 0
    for category, pages in CATEGORIES.items():
        cat_dir = FIXTURE_ROOT / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        for filename, label, bg in pages:
            dest = cat_dir / filename
            if not dest.exists():
                _draw_page(dest, label, bg)
                print(f"  Created: {dest.relative_to(FIXTURE_ROOT.parent)}")
                created += 1
            else:
                print(f"  Exists:  {dest.relative_to(FIXTURE_ROOT.parent)}")
    print(f"\nDone. {created} new fixture image(s) created.")


if __name__ == "__main__":
    main()
