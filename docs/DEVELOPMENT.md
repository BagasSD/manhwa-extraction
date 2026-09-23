# Development Guide — Manhwa Context Extractor

Practical, local setup instructions. For *what* to build, see
`docs/PRD.md`; for *how it's organized*, see `docs/ARCHITECTURE.md`; for
*what to build next*, see `docs/TASKS.md`.

## Prerequisites

- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com) installed locally (needed starting
  Phase 1), configured to use the `gemma4:31b-cloud` model
- An Intel MacBook is the reference target — do not assume Apple Silicon
  (see `docs/PRD.md` §3)

## Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # adjust OLLAMA_* values once Phase 1 lands
uvicorn app.main:app --reload --port 8000
```

- Health check: `GET http://localhost:8000/health`
- Run tests: `cd backend && pytest`
- Add new services under `app/services/`, one responsibility per module
  (see `docs/ARCHITECTURE.md` §2)

## Frontend

```bash
cd frontend
npm install
cp .env.example .env           # VITE_API_BASE_URL, defaults to :8000
npm run dev                     # http://localhost:5173
npm run build                   # production build
```

The app shows "Backend: connected" on load once the FastAPI server is
running — this is the Phase 0 smoke test built into `src/App.tsx`.

## Environment Variables Reference

| Variable | Default | Used by |
|---|---|---|
| `APP_ENV` | `development` | backend |
| `CORS_ORIGINS` | `http://localhost:5173` | backend |
| `OLLAMA_HOST` | `http://localhost:11434` | backend (Phase 1+) |
| `OLLAMA_MODEL` | `gemma4:31b-cloud` | backend (Phase 1+) |
| `OLLAMA_THINK` | `false` | backend (Phase 1+) |
| `OLLAMA_TEMPERATURE` | `0` | backend (Phase 1+) |
| `OLLAMA_VISUAL_TOKENS` | `1120` | backend (Phase 1+) |
| `EXTRACTION_PREPROCESS_MODE` | `original` | backend: default preprocessing (`tiled` = crop + upscale) |
| `EXTRACTION_STRUCTURED_OUTPUT` | `true` | backend: send the page JSON schema as Ollama `format` |
| `EXTRACTION_MAX_TEMPERATURE` | `0.2` | backend: temperature cap for page extraction |
| `EXTRACTION_TILE_MAX_SEGMENTS` | `8` | backend: `tiled` segments per page |
| `EXTRACTION_TILE_MIN_WIDTH` | `1024` | backend: `tiled` segments are upscaled to this width (max 3x) |
| `EXPORT_EXCLUDED_TEXT_TYPES` | `["sfx"]` | backend: text types left out of TXT/JSON exports and chapter context (still kept in review) |
| `VITE_API_BASE_URL` | `http://localhost:8000` | frontend |

All values are read from environment/`.env` — never hard-code them in
code (`AGENTS.md` rule set, `docs/ARCHITECTURE.md` §3).

## Data & Persistence

No database. Everything is filesystem JSON under `data/`:

```text
data/chapters/chapter-001.json
data/results/chapter-001/page-001.raw.json
data/results/chapter-001/page-001.json
data/results/chapter-001/context.json
```

`data/*` is gitignored except `.gitkeep` placeholders — it's generated at
runtime, not source.

**Never overwrite raw model output.** Corrections are stored alongside
the raw result, never in place of it (see `docs/PRD.md` §9.1). This
matters for future benchmarking (`docs/PRD.md` §15).

## Testing Conventions

- Backend: `pytest`, tests live in `backend/tests/`, mirroring
  `backend/app/`. Mock Ollama in integration tests — don't require the
  real cloud model for every test run (`docs/PRD.md` §14).
- Fixture manhwa pages go in `tests/fixtures/<category>/` (categories
  listed in `docs/PRD.md` §14.1).
- Every new backend service needs unit tests before a phase is
  considered complete.

## Working Phase by Phase

1. Check `docs/TASKS.md` for the next unfinished phase and its
   acceptance criteria.
2. Hand the agent a task using the template in `docs/TASKS.md` (read
   docs → scope → requirements → acceptance criteria → explicit
   exclusions).
3. After the agent finishes: run backend tests (`pytest`) and a frontend
   type-check/build (`npx tsc --noEmit`, `npm run build`) before moving
   on.
4. Update the phase's checkbox/status in `docs/TASKS.md`.

## Troubleshooting

- **Frontend shows "Backend: unreachable"** — confirm `uvicorn` is
  running on the port in `VITE_API_BASE_URL`, and that `CORS_ORIGINS` in
  the backend `.env` includes the frontend's origin.
- **Ollama errors (Phase 1+)** — confirm `ollama` is running locally and
  `OLLAMA_HOST`/`OLLAMA_MODEL` in `backend/.env` are correct; cloud calls
  to `gemma4:31b-cloud` require Ollama Cloud connectivity.
- **A batch page fails repeatedly** — check `docs/PRD.md` §13.1 (retry
  policy): after 3 attempts a page becomes `status = manual_review`
  instead of blocking the rest of the batch.
- **Pages come back with empty `texts`** — run
  `python scripts/diagnose_text_extraction.py <page image> --legacy-json`
  from `backend/`. It prints what is sent to the model, the raw answer vs.
  the parsed texts, a crop test and a `tiled` run, and ends with a verdict
  (see `docs/text-extraction-upgrade-plan-v2.md` §8). Pages whose answer
  still looks like missed text after all retries are kept with
  `review_flags` and show as `manual_review`. Saving a correction clears them.
- **Comparing extraction strategies** — `POST /benchmark/run` with e.g.
  `{"modes": ["original", "tiled"]}` reports text recall against the
  ground truth in `tests/fixtures/**/expected.json`. Regenerate the synthetic
  regression pages with `python tests/fixtures/generate_fixtures.py`.
