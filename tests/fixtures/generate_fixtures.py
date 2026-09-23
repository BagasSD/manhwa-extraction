"""
Script to generate synthetic fixture images for benchmarking tests.

Creates simple PIL images in tests/fixtures/ subdirectories matching
the fixture dataset structure from PRD §14.1.

Run from the project root:
    python tests/fixtures/generate_fixtures.py
"""
from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# Text-extraction regression set (docs/text-extraction-upgrade-plan-v2.md §6)
#
# Fixed pages with known ground-truth text, varying text density: long
# narration, short dialogue, SFX only, no text at all, small text, a system
# window, a tall webtoon strip and a mixed page. `regression/expected.json` is
# read by the benchmark (POST /benchmark/run) to report text recall, missed-text
# pages and hallucinated-text pages per preprocessing mode, so a change can be
# compared before/after on the same pages. Synthetic pages are a floor, not a
# substitute: put real manhwa pages in their own folder (e.g. fixtures/real/)
# with its own expected.json; this script rewrites regression/expected.json.
# ---------------------------------------------------------------------------

REGRESSION_DIR = FIXTURE_ROOT / "regression"
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _figure(draw: ImageDraw.ImageDraw, cx: int, top: int, color: tuple[int, int, int]) -> None:
    draw.ellipse([cx - 55, top, cx + 55, top + 100], fill=color, outline=BLACK, width=3)
    draw.rectangle([cx - 70, top + 100, cx + 70, top + 330], fill=color, outline=BLACK, width=3)


def _bubble(draw: ImageDraw.ImageDraw, box: list[int], text: str, size: int, thought: bool = False) -> None:
    draw.ellipse(box, fill=WHITE, outline=BLACK, width=3)
    if not thought:
        # Tail pointing down toward the speaker
        mid = (box[0] + box[2]) // 2
        draw.polygon([(mid - 15, box[3] - 6), (mid + 15, box[3] - 6), (mid, box[3] + 40)], fill=WHITE, outline=BLACK)
    center = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
    draw.multiline_text(center, text, fill=BLACK, font=_font(size), anchor="mm", align="center")


def _text_box(
    draw: ImageDraw.ImageDraw,
    box: list[int],
    text: str,
    size: int,
    fill: tuple[int, int, int] = WHITE,
    ink: tuple[int, int, int] = BLACK,
) -> None:
    draw.rectangle(box, fill=fill, outline=BLACK, width=3)
    center = ((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
    draw.multiline_text(center, text, fill=ink, font=_font(size), anchor="mm", align="center", spacing=8)


def _canvas(width: int, height: int, bg: tuple[int, int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (width, height), color=bg)
    return img, ImageDraw.Draw(img)


def _long_narration() -> Image.Image:
    img, d = _canvas(800, 1100, (60, 60, 75))
    d.polygon([(0, 1100), (180, 700), (330, 820), (520, 600), (800, 900), (800, 1100)], fill=(35, 35, 45))
    _text_box(
        d, [60, 80, 740, 420],
        "The war had ended ten years ago,\nbut the city never recovered.\n"
        "Nobody remembered who fired first.\nOnly the ruins remained.",
        30,
    )
    return img


def _short_dialogue() -> Image.Image:
    img, d = _canvas(800, 1100, (225, 235, 245))
    _figure(d, 220, 600, (80, 60, 40))
    _figure(d, 590, 600, (190, 160, 60))
    _bubble(d, [60, 180, 380, 420], "Wait!", 44)
    _bubble(d, [430, 220, 760, 450], "Who are\nyou?", 38)
    return img


def _sfx_only() -> Image.Image:
    img, d = _canvas(800, 1000, (250, 225, 190))
    d.regular_polygon((400, 560, 300), n_sides=12, fill=(250, 140, 40), outline=BLACK)
    d.text((400, 540), "BOOM!!", fill=(160, 20, 20), font=_font(150), anchor="mm", stroke_width=6, stroke_fill=WHITE)
    return img


def _no_text() -> Image.Image:
    img, d = _canvas(800, 1000, (200, 220, 200))
    d.rectangle([20, 20, 780, 980], outline=BLACK, width=4)
    _figure(d, 300, 420, (70, 90, 60))
    d.line([(390, 560), (700, 380)], fill=(120, 120, 130), width=12)  # sword
    return img


def _small_text() -> Image.Image:
    img, d = _canvas(800, 1100, (240, 240, 235))
    d.rectangle([150, 380, 650, 1100], fill=(170, 170, 180), outline=BLACK, width=3)  # building
    _text_box(d, [300, 420, 500, 470], "PHARMACY", 16, fill=(40, 120, 60), ink=WHITE)
    _text_box(d, [30, 30, 270, 70], "Seoul, 3 years later", 13)
    return img


def _system_window() -> Image.Image:
    img, d = _canvas(800, 1000, (20, 25, 45))
    _text_box(
        d, [120, 300, 680, 620], "[Quest Complete]\nReward: 300 EXP", 34,
        fill=(30, 70, 140), ink=(220, 240, 255),
    )
    return img


def _tall_strip() -> Image.Image:
    img, d = _canvas(720, 4200, WHITE)
    panels = [(40, 1000), (1100, 2050), (2150, 2550), (2650, 4150)]
    colors = [(210, 215, 230), (190, 200, 215), (40, 40, 50), (205, 195, 185)]
    for (top, bottom), color in zip(panels, colors):
        d.rectangle([30, top, 690, bottom], fill=color, outline=BLACK, width=4)
    _figure(d, 360, 550, (70, 60, 50))
    _bubble(d, [120, 120, 600, 380], "Did you hear\nthat?", 22)
    _figure(d, 250, 1600, (90, 70, 60))
    _bubble(d, [260, 1180, 680, 1420], "It came from\nthe basement.", 22)
    _text_box(d, [230, 2310, 490, 2380], "Meanwhile...", 18)
    _figure(d, 450, 3500, (60, 50, 45))
    _bubble(d, [80, 2750, 520, 2990], "Stay behind\nme.", 22)
    return img


def _mixed() -> Image.Image:
    img, d = _canvas(800, 1200, (230, 225, 215))
    _text_box(d, [40, 40, 300, 110], "Day 1.", 30)
    _text_box(d, [560, 160, 740, 230], "EXIT", 34, fill=(30, 140, 60), ink=WHITE)
    _figure(d, 250, 780, (80, 60, 40))
    _bubble(d, [60, 420, 420, 640], "Let's go.", 36)
    for i, r in enumerate((10, 16, 22)):  # thought-bubble dots
        d.ellipse([560 - r + i * 25, 770 - r - i * 45, 560 + r + i * 25, 770 + r - i * 45], fill=WHITE, outline=BLACK)
    _bubble(d, [450, 380, 780, 620], "(I hope this\nworks...)", 30, thought=True)
    return img


# filename -> (drawer, ground-truth texts in reading order, what the page tests)
REGRESSION_PAGES = {
    "long_narration.png": (
        _long_narration,
        [
            "The war had ended ten years ago, but the city never recovered.",
            "Nobody remembered who fired first.",
            "Only the ruins remained.",
        ],
        "long narration box",
    ),
    "short_dialogue.png": (_short_dialogue, ["Wait!", "Who are you?"], "two short speech bubbles"),
    "sfx_only.png": (_sfx_only, ["BOOM!!"], "SFX only, no bubbles"),
    "no_text.png": (_no_text, [], "no text at all (must not hallucinate)"),
    "small_text.png": (_small_text, ["Seoul, 3 years later", "PHARMACY"], "small caption + sign"),
    "system_window.png": (_system_window, ["[Quest Complete]", "Reward: 300 EXP"], "system/UI window"),
    "tall_strip.png": (
        _tall_strip,
        ["Did you hear that?", "It came from the basement.", "Meanwhile...", "Stay behind me."],
        "tall 720x4200 webtoon strip (full-page downscale makes text illegible)",
    ),
    "mixed.png": (
        _mixed,
        ["Day 1.", "EXIT", "Let's go.", "(I hope this works...)"],
        "narration + sign + speech + thought",
    ),
}


def generate_regression_set() -> int:
    """Create missing regression pages and (re)write regression/expected.json."""
    REGRESSION_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    expected: dict[str, dict[str, object]] = {}
    for filename, (drawer, texts, note) in REGRESSION_PAGES.items():
        dest = REGRESSION_DIR / filename
        if not dest.exists():
            drawer().save(dest, format="PNG", optimize=True)
            print(f"  Created: {dest.relative_to(FIXTURE_ROOT.parent)}")
            created += 1
        else:
            print(f"  Exists:  {dest.relative_to(FIXTURE_ROOT.parent)}")
        expected[filename] = {"texts": texts, "note": note}

    (REGRESSION_DIR / "expected.json").write_text(
        json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return created


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
    write_category_expected()
    created += generate_regression_set()
    print(f"\nDone. {created} new fixture image(s) created.")


def write_category_expected() -> None:
    """Ground truth for the category pages above: the bubble text plus the small label."""
    expected = {
        f"{category}/{filename}": {"texts": ["Don't leave!", label[:50]]}
        for category, pages in CATEGORIES.items()
        for filename, label, _bg in pages
    }
    (FIXTURE_ROOT / "expected.json").write_text(
        json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
