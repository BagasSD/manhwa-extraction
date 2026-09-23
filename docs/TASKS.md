# Tasks — Manhwa Context Extractor

This document breaks the project into sequential phases for AI coding
agents (Claude Code, Antigravity, Kiro, etc.). **Give an agent one task
per session, in order — never "build the whole application."**

## Implementation Order

```text
0. Bootstrap                 ✅ done
1. Ollama Service             ✅ done
2. Single Page Extraction     ✅ done
3. Persistence (chapter/page) ✅ done
4. Review UI                  ✅ done
5. Manual Correction          ✅ done
6. Character Tracking         ✅ done
7. Batch Processing         ✅ done
8. Chapter Context         ✅ done
9. Export                    ✅ done
10. Benchmark / Optimization ✅ done
```

Do not skip directly to a later phase. Do not implement future phases
unless explicitly requested.

---

## Phase 0 — Repository Bootstrap ✅

Project structure, FastAPI, React, configuration, environment variables,
README, AGENTS.md, health endpoint.

**Acceptance:** Backend starts. Frontend starts. `GET /health` returns
200. — **Met**, see project root `README.md`.

---

## Phase 1 — Ollama Service ✅

Implement `OllamaService`: connection, model configuration, image
encoding, request, response extraction, timeout, errors.

**Acceptance:** A local test image can be sent to Gemma; a response is
returned. — **Met**, unit tested via mocked Ollama responses.

---

## Phase 2 — Page Extraction ✅

Pipeline: `image → Gemma → JSON → Pydantic → save`.

**Acceptance:** Valid JSON; characters extracted; text extracted; scene
extracted; raw result preserved. — **Met**, unit tested via mocked extraction pipeline.

---

## Phase 3 — Chapter/Page Management ✅

Chapter creation, page discovery, page ordering, page status, result
persistence.

**Acceptance:** A folder containing 100 images becomes a chapter. — **Met**, tested with 100 pages natural ordering and REST APIs.

---

## Phase 4 — Review UI ✅

Page viewer, text overlay, character overlay, scene panel, editable
fields.

**Acceptance:** User can inspect and correct a page without touching
JSON manually. — **Met**, full 3-column interactive Review UI built with React/TypeScript.

---

## Phase 5 — Correction Persistence ✅

Text/speaker/character/scene correction; save/reload.

**Acceptance:** User correction survives application restart. Raw AI
output remains intact. — **Met**, tested with PUT endpoint, filesystem persistence, and raw preservation.

---

## Phase 6 — Character Tracking ✅

Known character list, stable IDs, new character detection, manual merge,
manual rename.

**Acceptance:** `c1` remains `c1` across multiple pages when appropriate.
— **Met**, tested with cross-page aggregation, rename/merge across all pages, and REST API endpoints. 67 tests passed.

---

## Phase 7 — Batch Processing ✅

Queue, progress, resume, retry, failed page handling.

**Acceptance:** A 100-page chapter can be processed without restarting
the entire chapter after one failure. — **Met**, tested with sequential queue execution, resume skipping completed pages, 3-tier retry policy, graceful failure recovery with manual_review status, job cancellation, character propagation, and full REST & UI integration. 75 tests passed.

---

## Phase 8 — Chapter Context ✅

`reviewed pages → aggregation → Gemma → chapter context`.

**Acceptance:** Chapter context contains major characters, events,
transitions and important dialogue. — **Met**, tested with token-optimized page payload generation (stripping bboxes/redundancies), Gemma chapter context synthesis, persistent storage in `context.json`/`context.raw.json`, editable PUT route, and frontend modal review UI. 79 tests passed.

---

## Phase 9 — Export ✅

JSON and TXT export. TXT optimized for downstream AI (see
`docs/PRD.md` §11).

**Acceptance:** Exported files contain full chapter metadata, roster, synthesized context, and page-by-page extractions. Downstream TXT export formats character dialogues and scenes cleanly for script generation. — **Met**, tested with `ExportService`, REST endpoints `/export/json` and `/export/txt`, filesystem storage under `data/exports/`, and direct download UI in ReviewToolbar. 84 tests passed.

---

## Phase 10 — Benchmark & Optimization ✅

Test prompt variants, preprocessing, visual token budget, full page vs.
crop, retry strategy. Only change the default strategy based on measured
results (see `docs/PRD.md` §15).

**Acceptance:** Benchmark service tests multiple preprocessing modes across fixture datasets, records JSON validity rate, latency, attempts, character/text counts, and computes recommended preprocessing modes. REST endpoints `/benchmark/run` and `/benchmark/results` persist and return run summaries. — **Met**, tested with `BenchmarkService`, API endpoints, Pydantic schemas, and frontend API client methods. 116 tests passed.


---

## Task Template

Use this shape for every task handed to an agent:

```text
Implement Phase X / Task Y from docs/PRD.md.

Read:
- docs/PRD.md
- docs/ARCHITECTURE.md
- AGENTS.md

Scope:
[exact feature]

Requirements:
[requirements]

Acceptance criteria:
[criteria]

Do not:
[list of things that must not be implemented]

After implementation:
1. Run tests.
2. Fix failures caused by this change.
3. Report files changed.
4. Report tests executed.
5. Report remaining issues.
```

---

## Example Agent Prompts

### Phase 1 prompt

```text
Read AGENTS.md, docs/PRD.md, docs/ARCHITECTURE.md and the existing
implementation.

Implement Phase 1: Ollama integration.

Create an isolated Ollama service responsible for:
- model configuration
- image encoding
- API request
- response handling
- timeout
- errors

Use gemma4:31b-cloud.

Do not implement the review UI or batch processing.

Add unit tests using mocked Ollama responses.

Run all tests.

Report changed files, tests and remaining issues.
```

### Phase 2 prompt

```text
Read AGENTS.md, docs/PRD.md, docs/ARCHITECTURE.md and the current code.

Implement Phase 2: single-page extraction.

Pipeline:
image → Ollama → structured JSON → Pydantic validation
→ raw result persistence → normalized result persistence

Use the page extraction prompt from prompts/page_extraction.txt.

Do not implement chapter-level context yet.

Add tests for:
- valid response
- invalid JSON
- missing fields
- malformed bbox
- Ollama failure

Run all tests.
```

Use the same pattern (read docs → scope → acceptance criteria → tests →
report) for every later phase.

---

## Important Agent Behavior — Guardrails

If an agent suggests introducing something out of scope, redirect it
back to the current architecture rather than letting it silently change
direction:

| Agent suggests | Correct response |
|---|---|
| "I think we should use PostgreSQL." | Not in current scope. Use filesystem JSON as defined in `docs/ARCHITECTURE.md`. |
| "Let's add PaddleOCR." | Not part of the current architecture. Gemma is the primary extraction engine. |
| "Let's add LLM summarization here." | Out of scope until the Chapter Context phase (Phase 8). |

See `AGENTS.md` for the full rule set every agent must follow on this
repo.
