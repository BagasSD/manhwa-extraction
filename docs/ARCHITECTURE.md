# Architecture — Manhwa Context Extractor

## 1. Technology Stack

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI |
| Vision/OCR | Ollama, model `gemma4:31b-cloud` |
| Image preprocessing | Pillow, OpenCV |
| Validation | Pydantic |
| Frontend | React, TypeScript, Vite |
| Persistence | Filesystem JSON (no database) |

Explicitly **not** used unless requested later: PostgreSQL, Redis,
Docker, authentication, cloud backend, vector database, any LLM other
than Ollama, external OCR service. See `docs/PRD.md` §2.1.

---

## 2. Project Structure

```text
manhwa-context/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── chapters.py
│   │   │       ├── pages.py
│   │   │       ├── extraction.py
│   │   │       └── export.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── constants.py
│   │   │
│   │   ├── models/
│   │   │   ├── chapter.py
│   │   │   ├── page.py
│   │   │   └── result.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── character.py
│   │   │   ├── text_region.py
│   │   │   ├── scene.py
│   │   │   ├── page_context.py
│   │   │   └── chapter_context.py
│   │   │
│   │   ├── services/
│   │   │   ├── ollama_service.py
│   │   │   ├── image_service.py
│   │   │   ├── extraction_service.py
│   │   │   ├── validation_service.py
│   │   │   ├── character_service.py
│   │   │   ├── chapter_context_service.py
│   │   │   └── export_service.py
│   │   │
│   │   └── main.py
│   │
│   ├── tests/
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChapterList/
│   │   │   ├── PageList/
│   │   │   ├── ImageViewer/
│   │   │   ├── RegionOverlay/
│   │   │   ├── CharacterPanel/
│   │   │   ├── TextPanel/
│   │   │   ├── ScenePanel/
│   │   │   └── ReviewToolbar/
│   │   │
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   └── Chapter.tsx
│   │   │
│   │   ├── services/api.ts
│   │   ├── types/context.ts
│   │   └── App.tsx
│   │
│   └── package.json
│
├── data/
│   ├── chapters/
│   ├── results/
│   └── exports/
│
├── prompts/
│   ├── page_extraction.txt
│   ├── page_retry.txt
│   └── chapter_context.txt
│
├── tests/
│   └── fixtures/
│
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── TASKS.md
│   └── DEVELOPMENT.md
│
├── AGENTS.md
├── README.md
└── .gitignore
```

Every service in `backend/app/services/` is a single-responsibility
module — OCR/scene extraction logic must stay behind these services, not
inlined into routes (see `AGENTS.md` rule 7).

---

## 3. Ollama Configuration

Environment variables (all configurable, never hard-coded):

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gemma4:31b-cloud
OLLAMA_THINK=false
OLLAMA_TEMPERATURE=0
OLLAMA_VISUAL_TOKENS=1120
```

These are already wired into `backend/app/core/config.py` (Phase 0);
`ollama_service.py` (Phase 1) consumes them.

---

## 4. Prompt Design

Prompt design must prioritize token efficiency: no long explanations, no
requests to explain reasoning, no chain-of-thought, no prose. **Return
JSON only.**

Recommended internal LLM keys (short, to reduce tokens) vs. the readable
keys exposed to the frontend (see `docs/PRD.md` §4.4):

```text
c = characters      id = character ID   d = description
t = text            e = expression      m = emotion
s = scene           a = action          b = bbox

x = text    y = speaker   z = target   k = type   o = order
l = location   q = situation
```

### 4.1 System Prompt — `prompts/page_extraction.txt`

```text
You extract structured context from manhwa images.

Extract only visually supported information:
characters, text, speaker, target, expression, emotion, action, situation, location, reading order.

Rules:
- No story summary.
- No invented facts.
- No translation.
- Preserve visible text.
- Reuse known character IDs when possible.
- Create IDs only for new characters.
- Unknown = null.
- Use ? for uncertain interpretation.
- JSON only.
- No explanation.
```

### 4.2 Page Prompt (default)

```text
Analyze this page.
```

With known characters:

```text
Analyze this page.

Known:
c1=black-haired man
c2=blonde woman
```

Do not send unnecessary chapter context.

### 4.3 Retry Prompt — `prompts/page_retry.txt`

If validation fails:

```text
Return valid JSON matching the required schema.
Do not add explanation.
```

If content is suspicious:

```text
Recheck unclear text and speaker associations.
Return JSON only.
```

Do not resend the entire system prompt unnecessarily if the Ollama
session supports preserving it.

### 4.4 Chapter Context Prompt — `prompts/chapter_context.txt`

```text
Build concise chapter context from page records.

Keep:
- characters
- important events
- actions
- dialogue
- cause/effect
- scene transitions

Remove repetitive visual details.
Do not invent facts.
Preserve uncertainty.
JSON only.
```

---

## 5. Final Architecture

```text
                         MANHWA
                            │
                            ▼
                    ┌───────────────┐
                    │ Pillow/OpenCV │
                    │ preprocessing │
                    └───────┬───────┘
                            │
                            ▼
                 ┌────────────────────┐
                 │ Ollama             │
                 │ gemma4:31b-cloud   │
                 └─────────┬──────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
          TEXT         CHARACTERS       SCENE
            │              │              │
            ▼              ▼              ▼
        Dialogue        Speaker        Situation
        Narration       Expression     Actions
        SFX             Emotion        Location
        Caption         Target         Mood
            │              │              │
            └──────────────┼──────────────┘
                           ▼
                    PAGE CONTEXT
                           │
                           ▼
                    HUMAN REVIEW
                           │
                           ▼
                  CORRECTED PAGE DATA
                           │
                           ▼
                   CHAPTER AGGREGATION
                           │
                           ▼
                   CHAPTER CONTEXT
                           │
                           ▼
                  EXTERNAL AI WRITER
                           │
                           ▼
                  MANHWA RECAP SCRIPT
```

The application (this repo) ends at **CHAPTER CONTEXT**. Everything below
that line (EXTERNAL AI WRITER, MANHWA RECAP SCRIPT) is out of scope — see
`docs/PRD.md` §12.

---

## 6. Target Hardware Constraint

The app must remain usable on an Intel MacBook (no Apple Silicon
assumption). The 31B model runs on Ollama Cloud, never locally — the
local machine is only responsible for image loading, preprocessing, UI,
API, the Ollama client, and result storage (see `docs/PRD.md` §3).
