"""
Diagnose empty `texts` on one page (docs/text-extraction-upgrade-plan-v2.md §2).

Runs the plan's Phase 1 checks against the real Ollama model and prints a
verdict. Each model call is a single attempt (no retries) so the raw first
answer is visible.

  1. Image size on disk vs. the size of each image actually sent to the model.
  2. Whether the model reports the "vision" capability.
  3. Full page through the extraction pipeline: raw answer vs. parsed texts.
  4. A crop of the page with a plain "read the text" prompt.
  5. The same page in "tiled" mode (crop + upscale).
  6. Optional (--legacy-json): full page in plain "json" mode, as before the
     structured-output fix, to see which keys the model invents on its own.

Usage (from backend/, with Ollama running and backend/.env configured):
    python scripts/diagnose_text_extraction.py path/to/page.png
    python scripts/diagnose_text_extraction.py page.png --crop 0,0,800,600 --legacy-json

A JSON report is written to data/diagnostics/.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.extraction_service import TILED_MODE, ExtractionService  # noqa: E402
from app.services.image_service import ImageService  # noqa: E402
from app.services.ollama_service import OllamaError, OllamaService  # noqa: E402
from app.services.validation_service import (  # noqa: E402
    TEXT_LIST_KEYS,
    SchemaValidationError,
    ValidationService,
)

CROP_PROMPT = (
    "Read all text visible in this image. Output only the text exactly as written, "
    "one line per text block. If there is no text, output NONE."
)
PREVIEW_CHARS = 600


def _payload_kb(images: list[Image.Image]) -> float:
    return sum(len(base64.b64encode(ImageService.image_to_bytes(img))) for img in images) / 1024


def _preview(text: str) -> str:
    text = text.strip()
    return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + " ..."


async def _run_extraction(
    service: ExtractionService, image: Image.Image, mode: str
) -> dict[str, Any]:
    """One extraction attempt; returns parsed counts plus the raw answer."""
    try:
        result = await service.extract_page(image, page_num=1, preprocess_mode=mode, max_retries=0)
    except (SchemaValidationError, OllamaError) as exc:
        return {"mode": mode, "error": f"{type(exc).__name__}: {exc}", "texts": []}

    raw_text = result.raw_text
    try:
        raw_json = ValidationService.extract_json(raw_text)
    except SchemaValidationError:
        raw_json = {}
    unrecognized = ValidationService.find_unrecognized_keys(raw_json)
    # Text found under an alias such as "visible_text" was dropped before the fix
    alias_keys = [k for k in TEXT_LIST_KEYS if k not in ("texts", "t") and raw_json.get(k)]
    ctx = result.page_context
    return {
        "mode": mode,
        "image_sizes": result.image_sizes,
        "texts": [t.text for t in ctx.texts],
        "has_text": ctx.has_text,
        "ocr_confidence": ctx.ocr_confidence,
        "visual_summary": ctx.visual_summary,
        "review_flags": ctx.review_flags,
        "unrecognized_keys": unrecognized,
        "text_alias_keys": alias_keys,
        "raw_response": raw_text,
    }


def _print_extraction(title: str, run: dict[str, Any]) -> None:
    print(f"\n[{title}]")
    if "error" in run:
        print(f"  ERROR: {run['error']}")
        return
    print(f"  images sent:      {run['image_sizes']}")
    print(f"  texts parsed:     {len(run['texts'])} {run['texts'][:6]}")
    print(f"  has_text:         {run['has_text']}   ocr_confidence: {run['ocr_confidence']}")
    print(f"  visual_summary:   {run['visual_summary']}")
    if run["text_alias_keys"]:
        print(f"  text under alias key(s) {run['text_alias_keys']} instead of \"texts\"")
    if run["unrecognized_keys"]:
        print(f"  UNRECOGNIZED KEYS in raw answer: {run['unrecognized_keys']}")
    for flag in run["review_flags"]:
        print(f"  flag: {flag}")
    print(f"  raw answer:       {_preview(run['raw_response'])}")


def _verdict(report: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    full, tiled, crop = report["full_page"], report["tiled"], report["crop"]
    full_n, tiled_n = len(full.get("texts", [])), len(tiled.get("texts", []))
    crop_read = crop.get("answer", "").strip().upper() not in ("", "NONE")

    if report["model"].get("vision") is False:
        findings.append("Model does not report the 'vision' capability: it may be ignoring the image. Use a vision model.")
    legacy = report.get("legacy_json") or {}
    if legacy.get("text_alias_keys"):
        findings.append(
            f"Plain JSON mode answers under {legacy['text_alias_keys']} instead of \"texts\": before the fix "
            "the parser dropped this text. Structured output + key aliases now keep it."
        )
    if not legacy.get("texts") and legacy.get("unrecognized_keys"):
        findings.append(
            f"Plain JSON mode puts content under unrecognized keys {legacy['unrecognized_keys']}: "
            "text may still be lost in parsing; add the key to TEXT_LIST_KEYS."
        )
    if full_n == 0 and crop_read:
        findings.append(
            "Text is readable in a crop but not on the full page: a resolution problem. "
            "Set EXTRACTION_PREPROCESS_MODE=tiled (crop + upscale)."
        )
    if tiled_n > full_n:
        findings.append(f"Tiled mode captured more texts ({tiled_n}) than the full page ({full_n}).")
    if full_n == 0 and tiled_n == 0 and not crop_read:
        findings.append(
            "The model could not read text even from an upscaled crop: the model's own OCR is the limit "
            "(plan Phase 4: separate OCR from reasoning)."
        )
    if full_n > 0 and not findings:
        findings.append("Full-page extraction returned texts; compare them against the page by eye.")
    return findings


async def diagnose(image_path: Path, crop_box: tuple[int, int, int, int] | None, legacy_json: bool) -> dict[str, Any]:
    settings = get_settings()
    image = ImageService.load_image(image_path)
    report: dict[str, Any] = {
        "image": str(image_path),
        "model_name": settings.OLLAMA_MODEL,
        "original_size": image.size,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

    # 1. What is actually sent
    print(f"Image: {image_path} ({image.width}x{image.height}, mode {image.mode})")
    original = ImageService.preprocess(image, mode="original")
    segments = ImageService.split_into_segments(
        image,
        max_segments=settings.EXTRACTION_TILE_MAX_SEGMENTS,
        min_width=settings.EXTRACTION_TILE_MIN_WIDTH,
    )
    print(f"  original mode sends 1 image {original.size}, ~{_payload_kb([original]):.0f} KB base64")
    print(
        f"  tiled mode sends {len(segments)} image(s) {[s.image.size for s in segments]}, "
        f"~{_payload_kb([s.image for s in segments]):.0f} KB base64"
    )
    print("  (The model resizes each image to its own input budget; a tall page sent whole loses small text.)")

    async with OllamaService(settings=settings) as ollama:
        # 2. Vision capability
        try:
            info = await ollama.show_model()
            capabilities = info.get("capabilities")
            vision = ("vision" in capabilities) if isinstance(capabilities, list) else None
            report["model"] = {"capabilities": capabilities, "vision": vision}
        except OllamaError as exc:
            report["model"] = {"error": str(exc), "vision": None}
        print(f"\nModel {settings.OLLAMA_MODEL}: {report['model']}")

        service = ExtractionService(settings=settings, ollama_service=ollama)

        # 3. Full page through the pipeline
        report["full_page"] = await _run_extraction(service, image, "original")
        _print_extraction("full page, pipeline", report["full_page"])

        # 4. Crop + plain prompt
        crop_img = image.crop(crop_box).convert("RGB") if crop_box else segments[0].image
        try:
            answer = (await ollama.generate(prompt=CROP_PROMPT, images=[crop_img])).get("response", "")
            report["crop"] = {"box": crop_box or "first tiled segment", "size": crop_img.size, "answer": answer}
        except OllamaError as exc:
            report["crop"] = {"box": crop_box, "error": str(exc), "answer": ""}
        print(f"\n[crop {report['crop'].get('box')} {crop_img.size}, plain prompt]")
        print(f"  answer: {_preview(report['crop'].get('answer') or report['crop'].get('error', ''))}")

        # 5. Tiled
        report["tiled"] = await _run_extraction(service, image, TILED_MODE)
        _print_extraction("tiled (crop + upscale), pipeline", report["tiled"])

        # 6. Legacy plain JSON mode
        if legacy_json:
            legacy_settings = settings.model_copy(update={"EXTRACTION_STRUCTURED_OUTPUT": False})
            legacy_service = ExtractionService(settings=legacy_settings, ollama_service=ollama)
            report["legacy_json"] = await _run_extraction(legacy_service, image, "original")
            _print_extraction("full page, plain json mode (pre-fix behaviour)", report["legacy_json"])

    report["verdict"] = _verdict(report)
    print("\nVerdict:")
    for line in report["verdict"]:
        print(f"  - {line}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", type=Path, help="Page image that came back with empty texts")
    parser.add_argument("--crop", help="Crop box x1,y1,x2,y2 around some text (default: first tiled segment)")
    parser.add_argument("--legacy-json", action="store_true", help="Also run the pre-fix plain JSON mode")
    args = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)  # review flags are printed below instead

    crop_box = tuple(int(v) for v in args.crop.split(",")) if args.crop else None
    if crop_box is not None and len(crop_box) != 4:
        parser.error("--crop needs four integers: x1,y1,x2,y2")

    report = asyncio.run(diagnose(args.image, crop_box, args.legacy_json))  # type: ignore[arg-type]

    out_dir = get_settings().DATA_DIR / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.image.stem}-{datetime.now():%Y%m%d-%H%M%S}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nReport: {out_path}")


if __name__ == "__main__":
    main()
