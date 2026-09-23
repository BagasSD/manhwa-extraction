"""Tests for the empty-`texts` fix (docs/text-extraction-upgrade-plan-v2.md).

Covers: output-key aliases, structured output, missing-text detection and
retry escalation, review flags, tiled (crop + upscale) preprocessing, and the
text-recall benchmark. Ollama is always mocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import numpy as np
import pytest
from PIL import Image

from app.core.config import Settings
from app.models.chapter import ChapterCreate
from app.schemas.benchmark import BenchmarkRunRequest, PreprocessMode
from app.schemas.page_context import PageContext
from app.schemas.text_region import TextRegion
from app.services.benchmark_service import BenchmarkService
from app.services.chapter_service import ChapterService
from app.services.extraction_service import ExtractionService, build_page_output_schema
from app.services.image_service import TILE_MAX_ASPECT, ImageSegment, ImageService
from app.services.ollama_service import OllamaResponseError, OllamaService
from app.services.validation_service import (
    SchemaValidationError,
    SuspiciousExtractionError,
    ValidationService,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    for sub in ("results", "prompts", "chapters", "data"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    return Settings(
        RESULTS_DIR=tmp_path / "results",
        PROMPTS_DIR=tmp_path / "prompts",
        CHAPTERS_DIR=tmp_path / "chapters",
        DATA_DIR=tmp_path / "data",
        OLLAMA_HOST="http://mock-ollama:11434",
        OLLAMA_MODEL="gemma4:31b-cloud",
    )


def _response(payload: dict[str, Any] | str) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"model": "gemma4:31b-cloud", "response": text}


_MISSING_TEXT_ANSWER = {
    "has_text": True,
    "characters": [{"id": "c1", "description": "man"}],
    "texts": [],
    "scene": {"situation": "c1 stands still"},
    "visual_summary": "A man stands next to a narration box.",
    "ocr_confidence": "low",
}
_GOOD_ANSWER = {
    "has_text": True,
    "characters": [{"id": "c1", "description": "man"}],
    "texts": [{"id": "t1", "text": "Wait!", "type": "speech", "speaker": "c1", "order": 1}],
    "scene": {"situation": "c1 shouts"},
    "visual_summary": "A man shouts.",
    "ocr_confidence": "high",
}


# ---------------------------------------------------------------------------
# Normalization: text the model returned under other keys must not be lost
# ---------------------------------------------------------------------------


class TestTextKeyAliases:
    def test_visible_text_key_with_content_field(self):
        ctx = ValidationService.validate_page_context({
            "characters": [{"id": "c1"}],
            "visible_text": [
                {"content": "That night, everything changed.", "text_type": "narration"},
                {"content": "WAIT!", "text_type": "speech", "speaker": "c1"},
            ],
        })
        assert [t.text for t in ctx.texts] == ["That night, everything changed.", "WAIT!"]
        assert [t.type for t in ctx.texts] == ["narration", "speech"]
        assert [t.id for t in ctx.texts] == ["t1", "t2"]
        assert ctx.texts[1].speaker == "c1"

    def test_dialogue_list_of_strings(self):
        ctx = ValidationService.validate_page_context({"dialogue": ["Hello.", "Who are you?"]})
        assert [t.text for t in ctx.texts] == ["Hello.", "Who are you?"]
        assert all(t.type == "unknown" for t in ctx.texts)
        assert [t.order for t in ctx.texts] == [1, 2]

    def test_top_level_text_string_split_per_line(self):
        ctx = ValidationService.validate_page_context({"text": "BOOM!\n\nRun!"})
        assert [t.text for t in ctx.texts] == ["BOOM!", "Run!"]

    def test_canonical_texts_key_wins_over_aliases(self):
        ctx = ValidationService.validate_page_context({
            "texts": [{"id": "t1", "text": "Real"}],
            "dialogue": ["Other"],
        })
        assert [t.text for t in ctx.texts] == ["Real"]

    def test_empty_texts_falls_through_to_alias(self):
        ctx = ValidationService.validate_page_context({"texts": [], "dialogues": ["Hi"]})
        assert [t.text for t in ctx.texts] == ["Hi"]

    @pytest.mark.parametrize("placeholder", ["null", "None", "unknown", "?", ""])
    def test_placeholder_speaker_and_target_become_null(self, placeholder: str):
        ctx = ValidationService.validate_page_context({
            "texts": [{"text": "Hi", "speaker": placeholder, "target": placeholder}],
        })
        assert ctx.texts[0].speaker is None
        assert ctx.texts[0].target is None

    def test_has_text_and_ocr_confidence(self):
        ctx = ValidationService.validate_page_context({"has_text": "true", "ocr_confidence": "LOW"})
        assert ctx.has_text is True
        assert ctx.ocr_confidence == "low"

    def test_invalid_ocr_confidence_becomes_null(self):
        ctx = ValidationService.validate_page_context({"has_text": False, "ocr_confidence": "excellent"})
        assert ctx.has_text is False
        assert ctx.ocr_confidence is None

    def test_old_results_without_new_fields_still_load(self):
        ctx = PageContext.model_validate({"page": 3, "texts": [{"text": "Hi"}]})
        assert ctx.has_text is None
        assert ctx.ocr_confidence is None
        assert ctx.review_flags == []


# ---------------------------------------------------------------------------
# Missing-text detection (plan v2 §6: "visual_summary mentions text, texts empty")
# ---------------------------------------------------------------------------


def _ctx(**kwargs: Any) -> PageContext:
    return ValidationService.validate_page_context(kwargs)


class TestMissingTextDetection:
    def test_has_text_true_with_empty_texts(self):
        issues = ValidationService.detect_missing_text(_ctx(has_text=True, texts=[]))
        assert any("has_text=true" in i for i in issues)

    @pytest.mark.parametrize(
        "summary",
        [
            "A warrior stands under a narrative text box.",
            "A caption at the top describes the city.",
            "The man said something to the woman.",
            "Two speech bubbles float above the characters.",
        ],
    )
    def test_summary_mentions_text_with_empty_texts(self, summary: str):
        issues = ValidationService.detect_missing_text(_ctx(visual_summary=summary))
        assert issues and all(i.startswith("Missing text:") for i in issues)

    def test_situation_mentions_dialogue(self):
        issues = ValidationService.detect_missing_text(_ctx(scene={"situation": "c1 and c2 in dialogue"}))
        assert any("'dialogue'" in i for i in issues)

    def test_no_text_page_is_not_flagged(self):
        ctx = _ctx(has_text=False, visual_summary="A lone swordsman stands in a forest.")
        assert ValidationService.detect_missing_text(ctx) == []

    def test_word_boundaries_avoid_false_positives(self):
        ctx = _ctx(visual_summary="In this context the pretext is a textured wall.")
        assert ValidationService.detect_missing_text(ctx) == []

    def test_texts_present_are_trusted(self):
        ctx = _ctx(has_text=True, texts=[{"text": "Hi"}], visual_summary="A caption box.")
        assert ValidationService.detect_missing_text(ctx) == []

    def test_empty_text_content_flagged(self):
        issues = ValidationService.detect_missing_text(_ctx(texts=[{"id": "t1", "text": "  "}]))
        assert any("'t1' has no transcribed content" in i for i in issues)

    def test_low_ocr_confidence_flagged(self):
        issues = ValidationService.detect_missing_text(
            _ctx(texts=[{"text": "Wa..."}], ocr_confidence="low")
        )
        assert any("low OCR confidence" in i for i in issues)

    def test_check_suspicious_raises_missing_text_error(self):
        with pytest.raises(SuspiciousExtractionError) as exc_info:
            ValidationService.validate_page_context(_MISSING_TEXT_ANSWER, check_suspicious=True)
        assert exc_info.value.is_missing_text
        assert exc_info.value.issues

    def test_other_anomalies_are_not_missing_text(self):
        with pytest.raises(SuspiciousExtractionError) as exc_info:
            ValidationService.validate_page_context(
                {"characters": [{"id": "c1"}], "texts": [{"text": "Hi", "speaker": "c9"}]},
                check_suspicious=True,
            )
        assert not exc_info.value.is_missing_text

    def test_flag_suspicious_keeps_result_with_review_flags(self):
        ctx = ValidationService.validate_page_context(_MISSING_TEXT_ANSWER, flag_suspicious=True)
        assert ctx.texts == []
        assert ctx.review_flags
        assert all(f.startswith("Missing text:") for f in ctx.review_flags)

    def test_unrecognized_keys_flagged_when_texts_empty(self):
        ctx = ValidationService.validate_page_context(
            {"characters": [], "speech_bubbles": [{"words": "Hello"}]}, flag_suspicious=True
        )
        assert any("unrecognized keys ['speech_bubbles']" in f for f in ctx.review_flags)

    def test_default_validation_has_no_review_flags(self):
        ctx = ValidationService.validate_page_context(_MISSING_TEXT_ANSWER)
        assert ctx.review_flags == []


# ---------------------------------------------------------------------------
# Image preprocessing: crop + upscale ("tiled")
# ---------------------------------------------------------------------------


def _busy_strip(width: int, height: int, gutters: list[tuple[int, int]]) -> Image.Image:
    """Noisy "art" everywhere except flat white gutter bands."""
    rng = np.random.default_rng(0)
    arr = rng.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    for top, bottom in gutters:
        arr[top:bottom] = 255
    return Image.fromarray(arr, "RGB")


class TestTiledPreprocessing:
    def test_original_mode_keeps_full_resolution(self):
        img = Image.new("RGB", (720, 4200), "white")
        assert ImageService.preprocess(img, mode="original").size == (720, 4200)

    def test_short_page_is_one_segment(self):
        segments = ImageService.split_into_segments(Image.new("RGB", (800, 1100)), min_width=800)
        assert len(segments) == 1
        assert segments[0].image.size == (800, 1100)
        assert (segments[0].top, segments[0].height) == (0, 1100)

    def test_tall_page_split_covers_page_without_overlap(self):
        segments = ImageService.split_into_segments(Image.new("RGB", (720, 4200), "white"))
        assert len(segments) == 4
        assert segments[0].top == 0
        for prev, cur in zip(segments, segments[1:]):
            assert cur.top == prev.top + prev.height
        assert segments[-1].top + segments[-1].height == 4200

    def test_narrow_segments_are_upscaled(self):
        segments = ImageService.split_into_segments(Image.new("RGB", (400, 600)), min_width=1024)
        assert segments[0].image.width == 1024
        assert segments[0].height == 600  # layout stays in original-page pixels

    def test_upscale_is_capped_at_3x(self):
        segments = ImageService.split_into_segments(Image.new("RGB", (200, 250)), min_width=1024)
        assert segments[0].image.size == (600, 750)

    def test_max_segments_cap(self):
        segments = ImageService.split_into_segments(Image.new("RGB", (500, 20000)), max_segments=5)
        assert len(segments) == 5

    def test_cuts_land_in_gutters(self):
        # Gutters sit away from the ideal cuts (1050, 2100, 3150) but inside the search window
        gutters = [(1200, 1280), (1900, 1980), (3300, 3380)]
        img = _busy_strip(720, 4200, gutters)
        segments = ImageService.split_into_segments(img, min_width=720)
        cuts = [s.top for s in segments[1:]]
        assert len(cuts) == 3
        for cut, (top, bottom) in zip(cuts, gutters):
            assert top <= cut < bottom

    def test_segments_respect_max_aspect(self):
        segments = ImageService.split_into_segments(Image.new("RGB", (720, 4200)), min_width=720)
        for seg in segments:
            assert seg.height <= 720 * TILE_MAX_ASPECT * 1.3  # cut may move within the search window

    def test_to_page_bbox_normalized(self):
        seg = ImageSegment(Image.new("RGB", (1024, 1422)), top=1000, height=1000, page_width=720, page_height=4000)
        # middle of the segment -> page y = 1000 + 500 = 1500 -> 375 on the 0-1000 scale
        assert seg.to_page_bbox([500, 250, 1000, 750]) == [375, 250, 500, 750]

    def test_to_page_bbox_pixels_of_upscaled_segment(self):
        seg = ImageSegment(Image.new("RGB", (1440, 2000)), top=1000, height=1000, page_width=720, page_height=4000)
        # 2x upscaled pixels: y 1000 -> 500 original -> page 1500 -> 375
        assert seg.to_page_bbox([1000, 360, 2000, 1080]) == [375, 250, 500, 750]


class TestTiledBboxNormalization:
    def _segments(self) -> list[ImageSegment]:
        img = Image.new("RGB", (100, 100))
        return [
            ImageSegment(img, top=0, height=1000, page_width=720, page_height=2000),
            ImageSegment(img, top=1000, height=1000, page_width=720, page_height=2000),
        ]

    def test_bbox_mapped_by_segment(self):
        ctx = ValidationService.validate_page_context(
            {"texts": [{"text": "Hi", "seg": 2, "bbox": [0, 100, 500, 900]}]},
            segments=self._segments(),
        )
        assert ctx.texts[0].bbox == [500, 100, 750, 900]

    def test_bbox_without_known_segment_dropped(self):
        ctx = ValidationService.validate_page_context(
            {"texts": [{"text": "A", "bbox": [0, 0, 10, 10]}, {"text": "B", "seg": 7, "bbox": [0, 0, 10, 10]}]},
            segments=self._segments(),
        )
        assert [t.bbox for t in ctx.texts] == [None, None]
        assert [t.text for t in ctx.texts] == ["A", "B"]

    def test_malformed_bbox_still_rejected_in_tiled_mode(self):
        with pytest.raises(SchemaValidationError):
            ValidationService.validate_page_context(
                {"characters": [{"id": "c1", "seg": 1, "bbox": [1, 2, 3]}]}, segments=self._segments()
            )


# ---------------------------------------------------------------------------
# Extraction pipeline
# ---------------------------------------------------------------------------


def _mock_ollama(*responses: Any) -> AsyncMock:
    mock = AsyncMock(spec=OllamaService)
    mock.generate.side_effect = list(responses)
    return mock


@pytest.mark.asyncio
class TestExtractionPipeline:
    async def test_structured_output_schema_and_low_temperature(self, settings: Settings):
        settings = settings.model_copy(update={"OLLAMA_TEMPERATURE": 0.7})
        mock = _mock_ollama(_response(_GOOD_ANSWER))
        service = ExtractionService(settings=settings, ollama_service=mock)
        await service.extract_page(Image.new("RGB", (400, 600)))

        kwargs = mock.generate.call_args.kwargs
        schema = kwargs["format"]
        assert isinstance(schema, dict)
        assert list(schema["properties"])[0] == "has_text"
        assert "texts" in schema["required"]
        text_item = schema["properties"]["texts"]["items"]
        assert text_item["properties"]["type"]["enum"][0] == "speech"
        assert "seg" not in text_item["properties"]
        assert kwargs["options"]["temperature"] == 0.2

    async def test_plain_json_mode_when_structured_output_disabled(self, settings: Settings):
        settings = settings.model_copy(update={"EXTRACTION_STRUCTURED_OUTPUT": False})
        mock = _mock_ollama(_response(_GOOD_ANSWER))
        await ExtractionService(settings=settings, ollama_service=mock).extract_page(Image.new("RGB", (40, 60)))
        assert mock.generate.call_args.kwargs["format"] == "json"

    async def test_schema_rejected_falls_back_to_plain_json(self, settings: Settings):
        mock = _mock_ollama(
            OllamaResponseError("invalid format", status_code=400, response_body="bad format"),
            _response(_GOOD_ANSWER),
            _response(_GOOD_ANSWER),
        )
        service = ExtractionService(settings=settings, ollama_service=mock)
        result = await service.extract_page(Image.new("RGB", (40, 60)))
        assert result.page_context.texts[0].text == "Wait!"
        assert result.attempts == 1

        # The next page goes straight to plain JSON mode
        await service.extract_page(Image.new("RGB", (40, 60)), page_num=2)
        formats = [call.kwargs["format"] for call in mock.generate.call_args_list]
        assert isinstance(formats[0], dict) and formats[1:] == ["json", "json"]

    async def test_non_format_errors_are_not_swallowed(self, settings: Settings):
        mock = _mock_ollama(OllamaResponseError("server down", status_code=500))
        with pytest.raises(OllamaResponseError):
            await ExtractionService(settings=settings, ollama_service=mock).extract_page(Image.new("RGB", (40, 60)))
        assert mock.generate.call_count == 1

    async def test_missing_text_retries_then_escalates_to_tiled(self, settings: Settings):
        mock = _mock_ollama(
            _response(_MISSING_TEXT_ANSWER),
            _response(_MISSING_TEXT_ANSWER),
            _response(_GOOD_ANSWER),
        )
        service = ExtractionService(settings=settings, ollama_service=mock)
        result = await service.extract_page(Image.new("RGB", (400, 600)), max_retries=2)

        assert result.attempts == 3
        assert result.preprocess_mode == "tiled"
        assert [t.text for t in result.page_context.texts] == ["Wait!"]
        assert result.page_context.review_flags == []

        calls = mock.generate.call_args_list
        assert "missed text" in calls[1].kwargs["prompt"]
        # Attempt 3: tiled -> segment instructions, upscaled image, "seg" in schema
        third = calls[2].kwargs
        assert "segment image(s)" in third["prompt"]
        assert third["images"][0].width == settings.EXTRACTION_TILE_MIN_WIDTH
        assert "seg" in third["format"]["properties"]["texts"]["items"]["properties"]

    async def test_non_text_anomaly_escalates_to_enhanced(self, settings: Settings):
        bad_ref = {**_GOOD_ANSWER, "texts": [{"id": "t1", "text": "Hi", "speaker": "c9"}]}
        mock = _mock_ollama(_response(bad_ref), _response(bad_ref), _response(_GOOD_ANSWER))
        result = await ExtractionService(settings=settings, ollama_service=mock).extract_page(
            Image.new("RGB", (40, 60)), max_retries=2
        )
        assert result.preprocess_mode == "enhanced"
        assert "nonexistent speaker 'c9'" in mock.generate.call_args_list[1].kwargs["prompt"]

    async def test_suspicious_last_attempt_kept_with_review_flags(self, settings: Settings):
        mock = _mock_ollama(_response(_MISSING_TEXT_ANSWER), _response(_MISSING_TEXT_ANSWER))
        service = ExtractionService(settings=settings, ollama_service=mock)
        result = await service.extract_page(Image.new("RGB", (40, 60)), max_retries=1, chapter_id="ch-1")

        assert result.page_context.texts == []
        assert result.page_context.review_flags
        saved = json.loads(Path(result.result_path).read_text(encoding="utf-8"))
        assert saved["review_flags"] == result.page_context.review_flags
        assert saved["has_text"] is True
        raw = json.loads(Path(result.raw_path).read_text(encoding="utf-8"))
        assert json.loads(raw["response"]) == _MISSING_TEXT_ANSWER

    async def test_tiled_mode_sends_segments_and_maps_bboxes(self, settings: Settings):
        answer = {
            **_GOOD_ANSWER,
            "texts": [
                {"id": "t1", "text": "Top", "type": "speech", "order": 1, "seg": 1, "bbox": [0, 0, 1000, 1000]},
                {"id": "t2", "text": "Bottom", "type": "speech", "order": 2, "seg": 4, "bbox": [0, 0, 1000, 1000]},
            ],
        }
        mock = _mock_ollama(_response(answer))
        service = ExtractionService(settings=settings, ollama_service=mock)
        result = await service.extract_page(
            Image.new("RGB", (720, 4200), "white"), preprocess_mode="tiled", max_retries=0
        )

        kwargs = mock.generate.call_args.kwargs
        assert len(kwargs["images"]) == 4
        assert "split into 4 segment image(s)" in kwargs["prompt"]
        assert len(result.image_sizes) == 4
        top, bottom = result.page_context.texts
        assert top.bbox[0] == 0 and top.bbox[2] < 300
        assert bottom.bbox[0] > 700 and bottom.bbox[2] == 1000


def test_output_schema_orders_and_requires_every_field():
    schema = build_page_output_schema()
    assert schema["required"] == list(schema["properties"])
    assert schema["properties"]["ocr_confidence"]["enum"] == ["high", "medium", "low", None]
    char_item = schema["properties"]["characters"]["items"]
    assert char_item["required"] == list(char_item["properties"])


# ---------------------------------------------------------------------------
# Review flags in chapter status + human review resolves them
# ---------------------------------------------------------------------------


def test_flagged_page_needs_review_until_human_saves(settings: Settings, tmp_path: Path):
    img_dir = tmp_path / "imgs"
    img_dir.mkdir()
    Image.new("RGB", (10, 10)).save(img_dir / "page_1.png")
    service = ChapterService(settings=settings)
    service.create_chapter(ChapterCreate(id="ch-flag", title="Flag", source_path=str(img_dir)))

    flagged = PageContext(page=1, review_flags=["Missing text: model reported low OCR confidence"])
    res_dir = settings.RESULTS_DIR / "ch-flag"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / "page-001.json").write_text(flagged.model_dump_json(), encoding="utf-8")

    page = service.get_page("ch-flag", 1)
    assert page.status == "manual_review"
    assert page.error_message.startswith("Needs review: Missing text")
    assert service.get_chapter("ch-flag").completed_pages == 1

    corrected = page.context.model_copy(update={"texts": [TextRegion(text="Wait!")]})
    saved = service.save_page_correction("ch-flag", 1, corrected)
    assert saved.status == "done"
    assert saved.context.review_flags == []


@pytest.mark.asyncio
async def test_batch_counts_flagged_pages_and_retry_failed_only_reextracts_them(
    settings: Settings, tmp_path: Path
):
    from app.models.batch import BatchExtractRequest
    from app.services.batch_service import BatchService
    from app.services.character_service import CharacterService

    img_dir = tmp_path / "batch_imgs"
    img_dir.mkdir()
    for i in (1, 2):
        Image.new("RGB", (20, 30)).save(img_dir / f"page_{i}.png")
    chapter_service = ChapterService(settings=settings)
    chapter_service.create_chapter(ChapterCreate(id="ch-flag-batch", title="Flags", source_path=str(img_dir)))

    mock = AsyncMock(spec=OllamaService)
    mock.generate.return_value = _response(_MISSING_TEXT_ANSWER)
    batch = BatchService(
        settings=settings,
        extraction_service=ExtractionService(settings=settings, ollama_service=mock),
        chapter_service=chapter_service,
        character_service=CharacterService(settings=settings),
    )

    batch.start_batch("ch-flag-batch", BatchExtractRequest(max_retries_per_page=1))
    await batch._jobs["ch-flag-batch"].task
    status = batch.get_batch_status("ch-flag-batch")
    assert status.completed_pages == 2
    assert status.failed_pages == 0
    assert status.manual_review_pages == 2
    assert "2 need manual review" in status.message
    assert [p.status for p in chapter_service.get_chapter("ch-flag-batch").pages] == ["manual_review"] * 2

    # "Retry failed only" picks the flagged pages up again; now the model reads the text
    mock.generate.return_value = _response(_GOOD_ANSWER)
    batch.start_batch("ch-flag-batch", BatchExtractRequest(retry_failed_only=True, max_retries_per_page=1))
    await batch._jobs["ch-flag-batch"].task
    pages = chapter_service.get_chapter("ch-flag-batch").pages
    assert [p.status for p in pages] == ["done", "done"]
    assert chapter_service.get_page("ch-flag-batch", 1).context.texts[0].text == "Wait!"


# ---------------------------------------------------------------------------
# Ollama model capability check (plan v2 §2: is the model vision-capable?)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"capabilities": ["completion", "vision"]}, True),
        ({"capabilities": ["completion"]}, False),
        ({"details": {}}, None),
    ],
)
async def test_supports_vision(settings: Settings, body: dict[str, Any], expected: bool | None):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/show"
        assert json.loads(request.content)["model"] == "gemma4:31b-cloud"
        return httpx.Response(200, json=body)

    client = httpx.AsyncClient(base_url="http://mock-ollama:11434", transport=httpx.MockTransport(handler))
    service = OllamaService(settings=settings, client=client)
    assert await service.supports_vision() is expected
    await client.aclose()


# ---------------------------------------------------------------------------
# Benchmark: text recall against a fixed ground-truth set (plan v2 §6)
# ---------------------------------------------------------------------------


class TestTextRecallBenchmark:
    def test_count_matched_texts_is_fuzzy_and_order_independent(self):
        expected = ["Don't leave!", "Who are you?", "BOOM!!"]
        extracted = ["who are you", "Dont leave!", "Something else"]
        assert BenchmarkService.count_matched_texts(expected, extracted) == 2

    def test_split_lines_match_a_multiline_expected_text(self):
        expected = ["The war had ended ten years ago, but the city never recovered."]
        extracted = ["The war had ended ten years ago,", "but the city never recovered."]
        assert BenchmarkService.count_matched_texts(expected, extracted) == 1

    def test_load_expected_from_root_and_subfolders(self, tmp_path: Path):
        (tmp_path / "expected.json").write_text(json.dumps({"a.png": {"texts": ["A"]}}), encoding="utf-8")
        sub = tmp_path / "regression"
        sub.mkdir()
        (sub / "expected.json").write_text(json.dumps({"b.png": {"texts": []}}), encoding="utf-8")
        assert BenchmarkService._load_expected_texts(tmp_path) == {"a.png": ["A"], "regression/b.png": []}

    def test_repo_regression_manifest_matches_fixture_files(self):
        expected = BenchmarkService._load_expected_texts(FIXTURE_ROOT)
        regression = {k: v for k, v in expected.items() if k.startswith("regression/")}
        assert len(regression) >= 5
        assert regression["regression/no_text.png"] == []
        for rel_path in expected:
            assert (FIXTURE_ROOT / rel_path).is_file(), rel_path

    @pytest.mark.asyncio
    async def test_run_reports_recall_missed_and_hallucinated_pages(self, settings: Settings, tmp_path: Path):
        fixtures = tmp_path / "fx"
        fixtures.mkdir()
        for name in ("dialogue.png", "blank.png"):
            Image.new("RGB", (60, 90)).save(fixtures / name)
        (fixtures / "expected.json").write_text(
            json.dumps({"dialogue.png": {"texts": ["Wait!", "Stop!"]}, "blank.png": {"texts": []}}),
            encoding="utf-8",
        )
        no_text = {"has_text": False, "texts": [], "visual_summary": "An empty panel."}
        mock = AsyncMock(spec=OllamaService)
        # Files are processed in sorted order: blank.png, then dialogue.png
        mock.generate.side_effect = [
            _response(_GOOD_ANSWER),  # original / blank.png -> hallucinated "Wait!"
            _response(no_text),  # original / dialogue.png -> missed both texts
            _response(no_text),  # tiled / blank.png
            _response(_GOOD_ANSWER),  # tiled / dialogue.png -> 1 of 2
        ]
        service = BenchmarkService(settings=settings, ollama_service=mock)
        run = await service.run(
            BenchmarkRunRequest(modes=[PreprocessMode.ORIGINAL, PreprocessMode.TILED], fixture_dir=str(fixtures))
        )

        original, tiled = run.mode_summaries
        assert original.avg_text_recall == 0.0
        assert original.missed_text_pages == 1
        assert original.hallucinated_text_pages == 1
        assert tiled.avg_text_recall == 0.5
        assert tiled.missed_text_pages == 0
        assert tiled.hallucinated_text_pages == 0
        assert run.recommended_mode == PreprocessMode.TILED

        blank = next(r for r in run.page_results if r.page_path == "blank.png" and r.mode == PreprocessMode.TILED)
        assert blank.expected_text_count == 0 and blank.text_recall is None
