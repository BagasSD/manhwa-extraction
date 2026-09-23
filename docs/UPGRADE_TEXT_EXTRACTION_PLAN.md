# Task: Enhance Manhwa Page Extraction

## Objective

Enhance the existing Manhwa Context Extractor so that each manhwa page produces a structured context containing both:

1. Visual context
2. OCR / text / dialogue context

The output will later be reviewed by the user and used as input for `chapter_context`, which will then be provided to an external AI script writer.

Do NOT generate the final YouTube recap script in this task.

---

# 1. First: Inspect Existing Project

Before changing anything, read:

- [`AGENTS.md`](http://AGENTS.md)
- `docs/[PRD.md](http://PRD.md)`
- `docs/[ARCHITECTURE.md](http://ARCHITECTURE.md)`
- `docs/[DEVELOPMENT.md](http://DEVELOPMENT.md)`
- `prompts/page_extraction.txt`
- `prompts/page_reply.txt`
- `prompts/chapter_context.txt`

Then inspect the existing:

- Pydantic schemas
- Ollama service
- extraction service
- persistence layer
- API routes
- frontend review UI
- export functionality
- tests

Do not rebuild the project from scratch.

Reuse the existing architecture wherever possible.

Before implementation, identify the exact files that need to be modified.

---

# 2. Core Extraction Goal

Gemma must extract information from each page image.

The extraction must contain:

```text
Characters
Text/OCR
Speaker
Target
Reading order
Expression
Emotion
Action
Location
Situation
Mood
Visual summary

```

The important change is that `texts` must become a meaningful structured representation rather than simply returning an empty array when dialogue/text exists.

---

# 3. Text Extraction

Each detected text region should have:

```json
{
  "id": "t1",
  "text": "I won't let you go.",
  "type": "speech",
  "speaker": "c1",
  "target": "c2",
  "bbox": [100, 200, 500, 350],
  "order": 1,
  "confidence": 0.92
}

```

Supported types:

```text
speech
thought
narration
caption
system
sfx
sign
unknown

```

Meaning:

```text
speech    = spoken dialogue
thought   = internal thought
narration = narration box
caption   = descriptive caption
system    = system/game/UI text
sfx       = sound effect
sign      = text visible in the environment
unknown   = type cannot be determined

```

---

# 4. OCR Rules

Gemma must:

- extract visible text
- preserve original text
- NOT translate text
- NOT rewrite text
- NOT summarize text
- NOT invent unreadable text
- preserve uncertainty
- use `null` when text cannot be determined
- detect relevant text regions
- determine reading order

If only part of a word/sentence is readable, preserve only what can actually be seen rather than hallucinating the missing text.

Example:

```json
{
  "text": "I won't le..."
}

```

is preferable to inventing the remainder.

---

# 5. Speaker and Target

For every dialogue where possible, identify:

```text
speaker
target

```

Example:

```json
{
  "text": "You!",
  "type": "speech",
  "speaker": "c2",
  "target": "c1",
  "order": 1
}

```

If the speaker cannot be determined:

```json
"speaker": null

```

If the target cannot be determined:

```json
"target": null

```

Do not guess based on story assumptions.

Use visual evidence such as:

- speech bubble tail
- bubble position
- character proximity
- panel composition
- thought bubble structure
- narration/caption styling

---

# 6. Character Extraction

Preserve the existing character structure.

Recommended:

```json
{
  "id": "c1",
  "description": "A black-haired young man wearing a dark coat.",
  "bbox": null,
  "expression": null,
  "emotion": null,
  "action": "Holding a sword"
}

```

Rules:

- use stable IDs such as `c1`, `c2`, `c3`
- reuse known character IDs
- create a new ID only when necessary
- never invent character names
- use `null` when unknown
- expression should describe visible facial expression
- emotion should only be assigned when visually supported
- action may be described when clearly visible

Do not infer emotion merely from an action.

For example:

```json
{
  "action": "Attacking",
  "emotion": null
}

```

is valid.

---

# 7. Known Characters

The backend should dynamically provide known characters when available.

Example:

```text
Known characters:

c1 = black-haired young man
c2 = blonde woman
c3 = white-haired demon

```

Do NOT hard-code these into the prompt files.

The model should use them to maintain character consistency across pages.

---

# 8. Scene

Preserve the existing scene structure:

```json
{
  "location": "Ruined urban environment",
  "situation": "A warrior stands among several demon-like entities.",
  "actions": [],
  "mood": "Ominous"
}

```

The scene must describe visually supported information.

Do not turn it into a long story summary.

Do not invent motivations or unseen events.

---

# 9. Visual Summary

Add:

```json
{
  "visual_summary": "A lone warrior stands among the ruins while several demon-like entities are shown around him."
}

```

Requirements:

- short
- factual
- visually supported
- no storytelling
- no invented motivations
- no long paragraph

---

# 10. Final Page Structure

The final normalized page result should approximately follow:

```json
{
  "page": 1,

  "characters": [
    {
      "id": "c1",
      "description": "Black-haired young man wearing a dark coat.",
      "bbox": null,
      "expression": null,
      "emotion": null,
      "action": "Holding a sword"
    }
  ],

  "texts": [
    {
      "id": "t1",
      "text": "I won't let you go.",
      "type": "speech",
      "speaker": "c1",
      "target": "c2",
      "bbox": null,
      "order": 1,
      "confidence": 0.92
    }
  ],

  "scene": {
    "location": "Ruined city",
    "situation": "c1 confronts c2.",
    "actions": [],
    "mood": "Tense"
  },

  "visual_summary": "A warrior confronts a demon in a ruined city."
}

```

The exact schema should follow the existing project's conventions.

Do not blindly replace an existing schema if equivalent structures already exist.

---

# 11. Update `page_extraction.txt`

Replace the empty prompt with a concise vision extraction prompt.

Use this content as the baseline:

```text
You are a visual context extractor for manhwa/comic pages.

Analyze the provided page image and extract only information visually supported by the image.

Extract:
- characters
- visible text
- text type
- speaker
- target
- reading order
- facial expression
- emotion
- action
- location
- situation
- mood
- visual summary

Rules:
- Preserve visible text accurately.
- Do not translate text.
- Do not rewrite or summarize dialogue.
- Do not invent text, names, events, or motivations.
- Reuse known character IDs when provided.
- Create new character IDs only when necessary.
- Use null when information is unknown.
- Use ? when an interpretation is uncertain.
- Do not infer emotion solely from actions or appearance.
- Do not provide a story summary.
- Do not explain reasoning.
- Return JSON only.

```

Keep the prompt token-efficient.

Do not add unnecessary explanations.

---

# 12. Update `page_reply.txt`

Use this as the baseline retry prompt:

```text
Re-check the provided manhwa page and return valid JSON.

Focus on:
- missing or incorrect text
- OCR accuracy
- text type
- speaker
- target
- reading order
- character consistency
- expression
- emotion
- action
- scene information

Rules:
- Use only visually supported information.
- Do not invent unreadable text.
- Do not invent names or events.
- Do not translate text.
- Use null when unknown.
- Preserve uncertainty.
- Do not explain reasoning.
- Return JSON only.

```

Keep this prompt shorter than the initial extraction prompt.

---

# 13. Update `chapter_context.txt`

Ensure it can consume the new `texts` structure.

The chapter context must preserve important dialogue.

Use this baseline:

```text
You are a chapter context organizer for a manhwa/comic.

Build structured chapter context from the provided page extraction results.

Keep:
- characters
- important events
- important dialogue
- speaker and target
- actions
- locations
- scene transitions
- cause/effect when supported

Rules:
- Prefer human-corrected data when available.
- Use only information from the provided page data.
- Do not invent facts, dialogue, characters, motivations, or events.
- Preserve uncertainty.
- Do not translate dialogue.
- Do not write the final YouTube script.
- Remove repetitive visual details.
- Keep chronological order.
- Return JSON only.

```

---

# 14. Ollama Integration

Verify the existing Ollama service supports:

```text
image
+
system prompt
+
dynamic known characters

```

The model remains:

```text
gemma4:31b-cloud

```

Do not introduce another model.

Do not introduce another OCR provider.

Do not add PaddleOCR/Tesseract as a replacement for Gemma.

Pillow/OpenCV may still be used for image preprocessing.

---

# 15. Validation

Update Pydantic/schema validation.

Validate:

### Characters

- valid ID
- valid bbox
- nullable expression
- nullable emotion
- nullable action

### Text

- unique text ID
- valid text type
- valid speaker reference
- valid target reference
- valid bbox
- valid order
- confidence between `0` and `1`

### Scene

- valid structure
- nullable fields where appropriate

### General

- page number valid
- valid JSON
- no unexpected malformed structures

If `speaker` or `target` references a nonexistent character, flag the result.

Do not silently invent a character to satisfy the reference.

---

# 16. Suspicious Extraction Detection

Add lightweight detection for:

```text
malformed JSON
empty response
duplicate text IDs
invalid confidence
invalid bbox
nonexistent character references
unexpectedly empty text extraction

```

Do not attempt complex semantic validation in application code.

If a result is suspicious, trigger the existing retry mechanism where appropriate.

---

# 17. Raw Output

Never overwrite the original AI response.

Maintain separate data:

```text
raw AI output
normalized AI output
human corrections

```

For example:

```text
page-001.raw.json
page-001.json

```

If the existing architecture has a correction model, reuse it.

The raw AI result must remain recoverable.

---

# 18. Human Review UI

Update the existing UI so the user can edit:

## Character

```text
ID
Description
Expression
Emotion
Action

```

## Text

```text
Text
Type
Speaker
Target
Order
BBox

```

## Scene

```text
Location
Situation
Actions
Mood

```

The user must be able to correct OCR manually.

This correction is important because the corrected data will become the source for chapter context.

---

# 19. Text Overlay

If `bbox` exists:

- render the text region on the image
- allow selecting the text region
- show the corresponding text in the review panel
- keep coordinates relative to the original image

Do not permanently alter the stored bbox because of UI resizing.

---

# 20. Export

Update JSON export to contain:

```text
characters
texts
scene
visual_summary

```

Update TXT export.

Example:

```text
PAGE 1

SCENE
Location: Ruined city
Situation: A warrior confronts a demon.

CHARACTERS
c1: black-haired warrior
c2: demon

TEXT
[1] c2 → c1
"You dare challenge me?"

[2] c1 → c2
"This ends here."

```

The TXT output should be easy for an external AI script writer to consume.

---

# 21. Tests

Add or update tests for:

```text
single dialogue
multiple dialogue
thought bubble
narration
caption
SFX
system text
sign
unknown text
ambiguous speaker
ambiguous target
unreadable text
multiple characters
speaker references
target references
reading order
bbox validation
confidence validation
raw output preservation
human corrections
TXT export

```

Mock Ollama responses.

Do not require the real cloud model for unit tests.

---

# 22. Important Scope Restrictions

Do NOT implement:

```text
final YouTube script generation
automatic translation
automatic storytelling
voice generation
RAG
vector database
database migration
authentication
deployment
fine-tuning
custom OCR model

```

The purpose of this task is only:

```text
MANHWA IMAGE
    ↓
GEMMA
    ↓
STRUCTURED PAGE CONTEXT
    ↓
HUMAN REVIEW

```

---

# 23. Implementation Order

Execute the task in this order:

1. Inspect current architecture.
2. Identify affected files.
3. Update schemas.
4. Update `page_extraction.txt`.
5. Update `page_reply.txt`.
6. Update `chapter_context.txt`.
7. Update Ollama/extraction service.
8. Update validation.
9. Update persistence.
10. Update API if required.
11. Update review UI.
12. Update text overlays.
13. Update export.
14. Add/update tests.
15. Run the full relevant test suite.
16. Fix failures.
17. Verify that existing functionality still works.

Do not perform unrelated refactoring.

---

# 24. Acceptance Criteria

The task is complete only when:

- Page extraction still works.
- Characters are extracted.
- Character IDs remain consistent when known characters are provided.
- Visible text is extracted.
- Text type is detected.
- Speaker is detected when visually supported.
- Target is detected when visually supported.
- Reading order is available.
- OCR text is preserved without translation.
- Unreadable text is not hallucinated.
- Expression can be extracted.
- Emotion is only assigned when visually supported.
- Actions are extracted.
- Location is extracted when supported.
- Situation is extracted.
- Mood is extracted when supported.
- Visual summary is generated.
- Human can edit all important extraction fields.
- Raw AI output remains preserved.
- Invalid/suspicious results can be retried.
- Chapter context can consume dialogue/text.
- JSON export contains the new text structure.
- TXT export contains dialogue and context.
- Tests pass.

---

# 25. Final Report

After implementation, report only:

### Changed

List the files modified/created.

### Implemented

Briefly describe what was implemented.

### Tests

List commands executed and their results.

### Remaining Issues

List only known issues that actually remain.

Do not claim the extraction is accurate unless it was actually tested with real pages.