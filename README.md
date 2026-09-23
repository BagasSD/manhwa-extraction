# Manhwa Context Extractor

Local-first application that extracts structured page-level context
(text, dialogue, speakers, characters, expressions, emotions, actions,
scene/location, reading order) from manhwa pages using Ollama +
`gemma4:31b-cloud`, for human review and downstream chapter-level
summarization.

This repository is being built incrementally, phase by phase. See
`docs/PRD.md`, `docs/ARCHITECTURE.md`, and `AGENTS.md` for the full plan.

**Current status: Phase 0 — Repository Bootstrap.**
Only the project skeleton, FastAPI backend, React frontend, configuration
and a health check are implemented. OCR/extraction, review UI, batch
processing, character tracking, and chapter context are not implemented yet.

## Requirements

- Python 3.11+
- Node.js 18+
- (Later phases) [Ollama](https://ollama.com) running locally, configured
  to use the `gemma4:31b-cloud` model.

## Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env           # adjust if needed
uvicorn app.main:app --reload --port 8000
```

Health check: http://localhost:8000/health

Run tests:

```bash
cd backend
pytest
```

## Frontend (React + TypeScript + Vite)

```bash
cd frontend
npm install
cp .env.example .env           # adjust VITE_API_BASE_URL if needed
npm run dev
```

Open http://localhost:5173 — it should show "Backend: connected" once the
backend is running.

## Project layout

```text
manhwa-context/
├── backend/    FastAPI app, services, tests
├── frontend/   React + TypeScript UI
├── data/       chapters / results / exports (filesystem persistence, no DB)
├── prompts/    LLM prompt templates
├── docs/       PRD, architecture, development notes
└── AGENTS.md   rules for AI coding agents working on this repo
```

## Principles (see AGENTS.md for the full list)

- Local-first: no database, no Docker, no auth, no extra LLMs.
- Ollama (`gemma4:31b-cloud`) is the only vision/OCR engine.
- AI output is never ground truth — every field is human-editable, and raw
  model output is never overwritten by corrections.
- Implement phases strictly in order; do not skip ahead.
