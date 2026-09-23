# PRD — Manhwa Context Extractor

## 1. Project Goal

Build a local-first application that analyzes manhwa pages using Ollama +
`gemma4:31b-cloud`.

The application must extract structured information from each page:

- visible text
- dialogue
- speaker
- dialogue target
- characters
- character identity
- facial expression
- emotion
- action
- location
- situation
- scene mood
- reading order
- uncertainty

The output is reviewed/corrected by the user and then converted into
chapter-level context.

**The application is not responsible for writing the final YouTube recap
script.** See section 15 (Script Writer Boundary).

Final workflow:

```text
Manhwa Images
    ↓
Image Preprocessing
    ↓
Gemma 4 via Ollama
    ↓
Page Context JSON
    ↓
Human Review / Correction
    ↓
Chapter Context
    ↓
External AI Script Writer
    ↓
Final Manhwa Recap Script
```

---

## 2. Core Principles

### 2.1 Local-first

The application itself runs locally. Stack: Python, FastAPI, React,
TypeScript, Ollama, Pillow, OpenCV, Pydantic.

Do **not** add, unless explicitly requested later: PostgreSQL, Redis,
Docker, authentication, a cloud backend, a vector database, an LLM other
than Ollama, or an external OCR service.

Ollama may communicate with Ollama Cloud because the configured model is
`gemma4:31b-cloud`. See `docs/ARCHITECTURE.md` §2 for the Ollama
configuration contract.

### 2.2 Gemma is the primary vision/OCR engine

Do not make PaddleOCR or Tesseract part of the core pipeline. Gemma
handles: text extraction, text region detection, character detection,
speaker association, expression, emotion, action, situation, location,
reading order. Pillow/OpenCV are preprocessing utilities only.

### 2.3 Extraction is different from storytelling

The model must distinguish:

- **Visible fact** — "A man points at another character."
- **Interpretation** — "The man appears to confront the other character."
- **Unknown** — "The reason for the confrontation cannot be determined."

The system must never force the model to invent missing information.

### 2.4 Human correction is a first-class feature

AI output is not ground truth. Every extracted value must be editable:
text, speaker, target, character ID, expression, emotion, action,
situation, location, reading order, region type.

---

## 3. Target Hardware

The application must remain usable on an Intel MacBook. Do not assume
Apple Silicon. The 31B cloud model must **not** be downloaded and executed
locally — the local machine only handles image loading, preprocessing,
UI, API, the Ollama client, and result storage.

---

## 4. Data Model

### 4.1 Character

```json
{
  "id": "c1",
  "description": "black-haired young man",
  "bbox": [100, 200, 400, 800],
  "expression": "angry",
  "emotion": "anger",
  "action": "pointing at c2"
}
```

Fields: `id, description, bbox, expression, emotion, action`. All fields
except `id` may be null.

### 4.2 Text Region

```json
{
  "text": "Don't leave!",
  "speaker": "c1",
  "target": "c2",
  "type": "sp",
  "bbox": [100, 50, 400, 150],
  "order": 1
}
```

Types: `sp` speech, `th` thought, `na` narration, `ca` caption, `ui` UI,
`sx` SFX, `uk` unknown.

Fields: `text, speaker, target, type, bbox, order`.

### 4.3 Scene

```json
{
  "location": "ruined building",
  "situation": "c1 tries to stop c2 from leaving",
  "actions": ["c1 points at c2", "c2 steps back"],
  "mood": "tense"
}
```

Keep scene descriptions short. Do not generate prose paragraphs.

### 4.4 Page Context Schema

```json
{
  "page": 12,
  "characters": [],
  "texts": [],
  "scene": {}
}
```

Use readable field names in the application schema exposed to the
frontend. Short keys (`c, t, s, id, d, e, m, a, b, x, y, z, k, o, l, q`)
may be used internally in the LLM prompt/output to reduce tokens — see
`docs/ARCHITECTURE.md` §3 for the mapping.

### 4.5 Character Identity

Do not require real character names. Use `c1, c2, c3...`. Use existing
IDs whenever the visual evidence is sufficient; create a new ID only when
a genuinely new character appears. Never invent a canonical character
name.

### 4.6 Uncertainty

Unknown information must be represented explicitly:

```json
{ "expression": null }
```

or, for uncertain interpretation:

```json
{ "situation": "c1 confronts c2?" }
```

Do not force certainty. Use `?` for uncertain interpretations.

---

## 5. Page Extraction Pipeline

```text
Image → Load → Validate → Optional resize → Send to Ollama
→ Receive response → Parse JSON → Pydantic validation
→ Save raw response → Save normalized result
```

Never discard the raw model response. Save both:

```text
data/results/chapter-001/page-001.raw.json
data/results/chapter-001/page-001.json
```

### 5.1 Image Preprocessing

Initially support: `original, resize, sharpen, contrast, upscale,
grayscale`. Do not automatically chain every operation. Configurable
strategies to start with: `original, upscale, enhanced, grayscale`.
Benchmark them later (see §11).

### 5.2 Full-page First

The first implementation must use `full page → Gemma`. Do not implement
crop-based OCR initially. After the baseline works, benchmark full page
vs. detect-regions-then-crop, and only keep crop processing if it
materially improves results.

---

## 6. API

```text
GET  /health

POST /chapters
GET  /chapters
GET  /chapters/{id}

GET  /chapters/{id}/pages
GET  /chapters/{id}/pages/{page}

POST /chapters/{id}/pages/{page}/extract
POST /chapters/{id}/pages/{page}/retry
POST /chapters/{id}/extract

PUT  /chapters/{id}/pages/{page}

POST /chapters/{id}/context
GET  /chapters/{id}/context

GET  /chapters/{id}/export/json
GET  /chapters/{id}/export/txt
```

---

## 7. Frontend MVP

```text
┌───────────────────────────────────────────────┐
│ Chapter                                        │
├───────────┬─────────────────────┬─────────────┤
│ Pages     │                     │ Context     │
│ 001 ✓     │     MANHWA IMAGE    │ Characters  │
│ 002 ✓     │    ┌───────────┐   │ Dialogue    │
│ 003 ⚠     │    │  bubble   │   │ Scene       │
│ 004       │    └───────────┘   │             │
└───────────┴─────────────────────┴─────────────┘
```

Prioritize functionality over visual polish.

### 7.1 Image Viewer

Must: display the original page; display character bounding boxes;
display text bounding boxes; allow selecting regions; maintain correct
image coordinate mapping; support zoom and pan. Overlay coordinates
always refer to the original image dimensions.

### 7.2 Review Panel

Character fields: ID, Description, Expression, Emotion, Action, Save.
Text fields: Text, Speaker, Target, Type, Order, Save.
Scene fields: Location, Situation, Mood, Actions (list), Save.
Everything must be editable.

### 7.3 Keyboard Shortcuts (add later, not during initial UI work)

`← / →` prev/next page · `E` edit selected · `D` delete selected ·
`A` add region · `R` rerun extraction · `S` save.

---

## 8. Batch Processing

Requirements: progress indicator, per-page status, retry failed page,
resume interrupted processing, skip already completed pages, cancel
processing.

```text
73 / 100
✓ 001  ✓ 002  ✓ 003 ...  ⚠ 073  ○ 074 ...
```

---

## 9. Persistence

No database initially — filesystem JSON only.

```text
data/
├── chapters/chapter-001.json          # chapter metadata
└── results/
    └── chapter-001/
        ├── page-001.raw.json
        ├── page-001.json
        └── context.json               # chapter context
```

### 9.1 Raw vs Corrected Data

Never overwrite raw model output:

```json
{
  "raw": { "text": "Dont leave!" },
  "corrected": { "text": "Don't leave!" }
}
```

(or maintain `model_result` / `user_correction` separately). This
distinction matters for future benchmarking.

---

## 10. Chapter Context Generation

After all pages are reviewed:

```text
Page JSON × N → Aggregation → Gemma → Chapter Context
```

Do not resend original images — send the structured page records.

```json
{
  "characters": [{ "id": "c1", "name": null, "description": "black-haired man" }],
  "events": [
    { "pages": [1, 3], "event": "c1 enters the building" },
    { "pages": [4, 8], "event": "c1 confronts c2" }
  ],
  "transitions": [{ "pages": [8, 9], "description": "scene changes from building to forest" }],
  "important_dialogue": []
}
```

### 10.1 Token Optimization for Chapter Context

Before sending page data to Gemma: remove empty fields, remove unchanged
character descriptions, remove duplicate actions, keep corrected text,
keep uncertain information, keep page numbers, keep important dialogue,
keep scene transitions. Do not send bounding boxes to this step — useful
for page review, not for chapter-level context.

---

## 11. Export

```text
JSON
TXT   — optimized for downstream AI, e.g.:

[PAGE 1]
CHARACTERS:
c1: black-haired man
DIALOGUE:
c1: "Don't leave!"
SCENE:
Location: ruined building
Situation: c1 tries to stop c2 from leaving.
[PAGE 2]
...
```

---

## 12. Script Writer Boundary

This project stops at **Chapter Context**. Do not implement script
generation. The eventual external AI receives Chapter Context + the
user's writing style instructions, and produces the final Indonesian
recap script. This keeps visual extraction separate from creative
writing.

---

## 13. Error Handling

Handle: Ollama unavailable, network failure, timeout, invalid JSON,
schema validation failure, empty response, image unreadable, unsupported
image, model error, rate limit, cloud unavailable. Never crash the entire
batch because one page fails — a page can have `status = failed` while
the rest continue.

### 13.1 Retry Policy

```text
attempt 1 — normal extraction
attempt 2 — short retry prompt
attempt 3 — alternative preprocessing
```

After 3 failures: `status = manual_review`. Do not retry indefinitely.

### 13.2 Logging

Log: page, processing time, model, preprocessing mode, request status,
response size, validation result, retry count. Do not log huge image
payloads or expose sensitive API credentials.

---

## 14. Testing Strategy

**Unit tests**: schema validation, JSON parsing, bbox validation,
character ID validation, page persistence, chapter persistence, export,
retry handling.

**Integration tests**: mock Ollama. Test `image → mocked Ollama → JSON →
persistence`. Do not require the real cloud model for every test.

### 14.1 Fixture Dataset

```text
tests/fixtures/
├── clean/
├── difficult/
├── small_text/
├── text_over_art/
├── multiple_characters/
├── no_dialogue/
└── sfx/
```

Start with ~20–50 pages, expand to 100+ for benchmarking.

---

## 15. Benchmark Metrics

OCR correctness, speaker correctness, character consistency, expression
usefulness, emotion usefulness, situation usefulness, reading-order
correctness, JSON validity, processing time/page, tokens/page, **manual
correction time/page** (the most important practical metric — the goal is
reducing the user's preparation time, not theoretical 100% accuracy).

### 15.1 Benchmark Modes

```text
A: Full page → Gemma
B: Full page + preprocessing → Gemma
C: Region crop → Gemma
D: Selective crop retry
```

Implement A first. Do not optimize prematurely.

---

## 16. Definition of Done (MVP)

```text
[x] User can select a chapter folder.
[x] Application detects pages.
[x] User can process one page with Gemma.
[x] Gemma extracts text.
[x] Gemma identifies characters.
[x] Gemma associates speakers.
[x] Gemma identifies expressions when visible.
[x] Gemma identifies emotions when reasonably supported.
[x] Gemma identifies actions.
[x] Gemma describes the situation.
[x] Gemma identifies location when supported.
[x] Reading order is available.
[x] Results are stored as JSON.
[x] Raw AI output is preserved.
[x] User can edit extracted information.
[x] User corrections persist.
[x] Character IDs can remain consistent across pages.
[x] Chapter can be processed in batch.
[x] Failed pages can be retried.
[x] Processing can resume.
[x] Reviewed pages can generate chapter context.
[x] JSON export works.
[x] TXT export works.
[x] Tests pass.
```

## 17. Explicitly Out of Scope for MVP

```text
[ ] Final YouTube script generation
[ ] Automatic story truth verification
[ ] Perfect character/speaker/emotion recognition
[ ] Custom vision model training / fine-tuning Gemma
[ ] Vector database / RAG
[ ] User accounts
[ ] Cloud deployment
[ ] Mobile application
[ ] Multi-user collaboration
[ ] Automatic translation
[ ] Automatic chapter summarization before review
```

## 18. Success Criteria

The real success metric is **not** "Gemma is 100% accurate." It is:

```text
Manhwa → structured context → human correction
```

being substantially faster than manually reading and recording the
information — less manual transcription, less manual note-taking, less
repeated reading, faster script preparation — while preserving the user's
control over the final story facts.
