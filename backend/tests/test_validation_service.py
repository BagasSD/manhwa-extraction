"""Unit tests for ValidationService and Schemas."""

import pytest

from app.schemas.character import Character
from app.schemas.text_region import TextRegion
from app.services.validation_service import (
    JSONExtractionError,
    SchemaValidationError,
    SuspiciousExtractionError,
    ValidationService,
)


class TestValidationService:
    """Tests for JSON extraction, abbreviation normalization, and Pydantic validation."""

    def test_extract_json_direct(self):
        raw = '{"page": 1, "characters": [], "texts": [], "scene": {}, "visual_summary": "A warrior stands."}'
        data = ValidationService.extract_json(raw)
        assert data["page"] == 1
        assert data["visual_summary"] == "A warrior stands."

    def test_extract_json_markdown_fence(self):
        raw = "```json\n{\"characters\": [{\"id\": \"c1\"}]}\n```"
        data = ValidationService.extract_json(raw)
        assert len(data["characters"]) == 1

    def test_extract_json_with_surrounding_text(self):
        raw = "Here is the extraction:\n{\"characters\": [{\"id\": \"c1\"}], \"texts\": []}\nHope this helps!"
        data = ValidationService.extract_json(raw)
        assert data["characters"][0]["id"] == "c1"

    def test_extract_invalid_json(self):
        with pytest.raises(JSONExtractionError):
            ValidationService.extract_json("not a valid json at all")

    def test_extract_empty_string(self):
        with pytest.raises(JSONExtractionError):
            ValidationService.extract_json("")

    def test_validate_canonical_page_context(self):
        payload = {
            "page": 2,
            "characters": [
                {
                    "id": "c1",
                    "description": "black-haired young man",
                    "bbox": [100, 200, 400, 800],
                    "expression": "angry",
                    "emotion": "anger",
                    "action": "pointing at c2",
                },
                {
                    "id": "c2",
                    "description": "blonde woman",
                    "bbox": [200, 300, 500, 900],
                    "expression": "shocked",
                    "emotion": "fear",
                    "action": "stepping back",
                },
            ],
            "texts": [
                {
                    "id": "t1",
                    "text": "Don't leave!",
                    "speaker": "c1",
                    "target": "c2",
                    "type": "speech",
                    "bbox": [100, 50, 400, 150],
                    "order": 1,
                    "confidence": 0.95,
                }
            ],
            "scene": {
                "location": "ruined building",
                "situation": "c1 tries to stop c2",
                "actions": ["c1 points at c2"],
                "mood": "tense",
            },
            "visual_summary": "c1 confronts c2 in a ruined building.",
        }
        ctx = ValidationService.validate_page_context(payload, page_num=2)
        assert ctx.page == 2
        assert len(ctx.characters) == 2
        assert ctx.characters[0].id == "c1"
        assert ctx.characters[0].bbox == [100, 200, 400, 800]
        assert len(ctx.texts) == 1
        assert ctx.texts[0].id == "t1"
        assert ctx.texts[0].text == "Don't leave!"
        assert ctx.texts[0].type == "speech"
        assert ctx.texts[0].confidence == 0.95
        assert ctx.scene.location == "ruined building"
        assert ctx.visual_summary == "c1 confronts c2 in a ruined building."

    def test_validate_abbreviated_keys(self):
        payload = {
            "p": 5,
            "c": [
                {
                    "id": "c1",
                    "d": "man with sword",
                    "b": [10, 20, 30, 40],
                    "e": "calm",
                    "m": "focus",
                    "a": "holding sword",
                }
            ],
            "t": [
                {
                    "x": "Wait.",
                    "y": "c1",
                    "z": None,
                    "k": "sp",
                    "b": [1, 2, 3, 4],
                    "o": 1,
                    "conf": 0.88,
                }
            ],
            "s": {
                "l": "forest",
                "q": "standoff",
                "a": ["drawing sword"],
                "m": "quiet",
            },
            "vs": "A swordsman in the forest.",
        }
        ctx = ValidationService.validate_page_context(payload, page_num=5)
        assert ctx.page == 5
        assert ctx.characters[0].description == "man with sword"
        assert ctx.characters[0].bbox == [10, 20, 30, 40]
        assert ctx.texts[0].id == "t1"
        assert ctx.texts[0].text == "Wait."
        assert ctx.texts[0].speaker == "c1"
        assert ctx.texts[0].type == "speech"
        assert ctx.texts[0].confidence == 0.88
        assert ctx.scene.location == "forest"
        assert ctx.scene.actions == ["drawing sword"]
        assert ctx.visual_summary == "A swordsman in the forest."

    def test_missing_fields_defaults(self):
        payload = {}
        ctx = ValidationService.validate_page_context(payload, page_num=10)
        assert ctx.page == 10
        assert ctx.characters == []
        assert ctx.texts == []
        assert ctx.scene.location is None
        assert ctx.visual_summary is None

    def test_text_types_all_supported(self):
        payload = {
            "texts": [
                {"id": "t1", "text": "Hello!", "type": "speech"},
                {"id": "t2", "text": "I should run...", "type": "thought"},
                {"id": "t3", "text": "Meanwhile at the base...", "type": "narration"},
                {"id": "t4", "text": "Chapter 1", "type": "caption"},
                {"id": "t5", "text": "[Quest Complete]", "type": "system"},
                {"id": "t6", "text": "BOOM!", "type": "sfx"},
                {"id": "t7", "text": "RESTRICTED AREA", "type": "sign"},
                {"id": "t8", "text": "???", "type": "unknown"},
                {"id": "t9", "text": "Legacy", "type": "sp"},
                {"id": "t10", "text": "Unrecognized", "type": "some_random_type"},
            ]
        }
        ctx = ValidationService.validate_page_context(payload, page_num=1)
        assert ctx.texts[0].type == "speech"
        assert ctx.texts[1].type == "thought"
        assert ctx.texts[2].type == "narration"
        assert ctx.texts[3].type == "caption"
        assert ctx.texts[4].type == "system"
        assert ctx.texts[5].type == "sfx"
        assert ctx.texts[6].type == "sign"
        assert ctx.texts[7].type == "unknown"
        assert ctx.texts[8].type == "speech"
        assert ctx.texts[9].type == "unknown"

    def test_dialogue_speaker_and_target_variations(self):
        payload = {
            "characters": [{"id": "c1"}, {"id": "c2"}],
            "texts": [
                {"id": "t1", "text": "Single dialogue", "speaker": "c1", "target": None, "order": 1},
                {"id": "t2", "text": "Targeted dialogue", "speaker": "c1", "target": "c2", "order": 2},
                {"id": "t3", "text": "Ambiguous speaker", "speaker": None, "target": "c1", "order": 3},
                {"id": "t4", "text": "Unreadable text I won't le...", "speaker": "c2", "target": None, "order": 4},
            ]
        }
        ctx = ValidationService.validate_page_context(payload, page_num=1)
        assert ctx.texts[0].speaker == "c1"
        assert ctx.texts[0].target is None
        assert ctx.texts[1].target == "c2"
        assert ctx.texts[2].speaker is None
        assert ctx.texts[3].text == "Unreadable text I won't le..."

    def test_reading_order_and_confidence(self):
        payload = {
            "texts": [
                {"id": "t1", "text": "First", "order": 1, "confidence": 0.99},
                {"id": "t2", "text": "Second", "order": 2, "confidence": 0.5},
                {"id": "t3", "text": "Third", "order": 3, "confidence": 0.0},
            ]
        }
        ctx = ValidationService.validate_page_context(payload, page_num=1)
        assert [t.order for t in ctx.texts] == [1, 2, 3]
        assert [t.confidence for t in ctx.texts] == [0.99, 0.5, 0.0]

    def test_confidence_validation_out_of_range(self):
        with pytest.raises(SchemaValidationError):
            ValidationService.validate_page_context({
                "texts": [{"id": "t1", "text": "Hi", "confidence": 1.5}]
            })
        with pytest.raises(SchemaValidationError):
            ValidationService.validate_page_context({
                "texts": [{"id": "t1", "text": "Hi", "confidence": -0.1}]
            })

    def test_malformed_bbox_length(self):
        with pytest.raises(SchemaValidationError):
            ValidationService.validate_page_context({
                "characters": [{"id": "c1", "bbox": [10, 20, 30]}]  # only 3 numbers
            })

    def test_malformed_bbox_non_numeric(self):
        with pytest.raises(SchemaValidationError):
            ValidationService.validate_page_context({
                "characters": [{"id": "c1", "bbox": [10, "invalid", 30, 40]}]
            })

    def test_detect_suspicious_duplicate_text_ids(self):
        payload = {
            "characters": [{"id": "c1"}],
            "texts": [
                {"id": "t1", "text": "Line 1"},
                {"id": "t1", "text": "Line 2"},
            ]
        }
        ctx = ValidationService.validate_page_context(payload, page_num=1)
        issues = ValidationService.detect_suspicious(ctx)
        assert any("Duplicate text IDs" in issue for issue in issues)

    def test_detect_suspicious_nonexistent_speaker(self):
        payload = {
            "characters": [{"id": "c1"}],
            "texts": [
                {"id": "t1", "text": "Who said this?", "speaker": "c99"},
            ]
        }
        ctx = ValidationService.validate_page_context(payload, page_num=1)
        issues = ValidationService.detect_suspicious(ctx, known_character_ids={"c1"})
        assert any("nonexistent speaker 'c99'" in issue for issue in issues)

    def test_validate_with_check_suspicious_raises(self):
        payload = {
            "characters": [{"id": "c1"}],
            "texts": [
                {"id": "t1", "text": "Hello", "speaker": "c99"},
            ]
        }
        with pytest.raises(SuspiciousExtractionError):
            ValidationService.validate_page_context(
                payload,
                page_num=1,
                known_character_ids={"c1"},
                check_suspicious=True,
            )
