# COMES — Conversational Candidate Understanding (PoC)

**Goal:** Build a *rich, conversational* profile of a candidate — not just keyword matching.  
Instead of stopping at “has Python,” we collect *how* they used it (ownership, impact, team context, stack choices), and store that understanding as structured JSON. This dataset can power:
- downstream **agent actions** (follow-up questions, summaries, recommendations), and
- **candidate embeddings** (search/ranking by genuine fit, not just keywords).

---

## Why “candidate understanding”?

Two resumes can list the same tools but reflect very different capability:
- What did they **own** vs **collaborate** on?
- What was the **impact** (metrics, lift, reduced cost, time-to-value)?
- What’s the **team context** (size, role, cross-functional partners)?
- What’s the **stack** (and at what depth/recency)?

This PoC uses **resume + dialogue** to iteratively fill those gaps and persist the results as a **rich profile** (loose schema with core fields + free-form `attributes`).

---

## High-level architecture

```
Client (CLI/UI)
    │
    ▼
FastAPI app  (backend/app/main.py)
    ├─ Parsing     → parser.py (LLM or heuristics), text_extract.py (PDF→text)
    ├─ Gaps        → gap_finder.py
    ├─ Q&A         → llm_agent.py (optional) + questioner.py (fallback)
    ├─ Updates     → updater.py (LLM structured updates + heuristics)
    ├─ Synthesis   → synthesizer.py
    ├─ DB access   → db.py, models.py, repo.py
    └─ Schemas     → schemas.py (Pydantic v2)
```

**Data model (essentials)**  
- `Profile`
  - `projects[]` (each job/project)
    - **core fields:** `title`, `period`, `team_size`, `stack`, `impact{delta|metric|details}`, `ownership`, `collaboration`
    - **attributes (dict):** keep **all** free-form keys produced by the LLM (nothing is lost)
  - `skills[]`: `name`, `depth`, `last_used`, `evidence[]`, and `attributes{...}`

**Policy:**  
- If the LLM proposes a known/core field → store on **core** and **mirror** into `attributes`.  
- Unknown/new keys → store under **attributes** (no data loss).  
- `gap_finder` treats **either core or attributes** as fulfilling a gap.

---

## Agent workflow (RAG + structured updates)

1) **Parsing** (resume → draft profile)  
   - `parse_resume_file`: extract text (`text_extract.py`) then build a *draft* `Profile` via `parser.py` (LLM or heuristic).

2) **Gap finding** (what to ask next)  
   - `gap_finder.py` identifies missing items: `ownership`, `stack_details`, `project_impact`, `team_context`, `skill_depth`, `skill_recency`, …
   - A gap is considered **filled if present on core OR in attributes**.

3) **Question generation**  
   - `llm_agent.py` (with optional RAG over resume text, current profile, and recent Q&A) produces *one focused question*.  
   - If LLM is off/unavailable, fallback to `questioner.py`.

4) **Answer interpretation → structured patches**  
   - User answers in natural language.  
   - `llm_agent.py` converts that answer into a **patch list**:
     ```json
     [
       {"path":"projects[Business Insight Analyst – Intern].ownership","value":"..."},
       {"path":"projects[Business Insight Analyst – Intern].team_size","value":4},
       {"path":"projects[Business Insight Analyst – Intern].tech","value":["MS SQL Server","PySpark","Power BI"]}
     ]
     ```
   - `updater.py` applies patches **in-place**:
     - Known/core → set core **and** mirror into `attributes` (e.g., `ownership`, `collaboration`).
     - Unknown → `attributes` (preserving nested paths).
     - `stack/tech` is merged & deduped; `impact` supports partial updates (e.g., only `delta`).

5) **Recompute gaps & (optional) synthesis**  
   - After updates, `gap_finder.py` recomputes remaining gaps.  
   - `synthesizer.py` can produce a narrative summary from the enriched profile.

---

## Requirements

- **Python** 3.11+ (3.12 recommended)
- **Poppler** (`pdftotext`) for PDF → text
- **OpenAI API key** if you want LLM features (parser, question, interpretation)

---

## Setup

```bash
# 1) Create venv
python3 -m venv .venv
source .venv/bin/activate

# 2) Install deps
pip install -r requirements.txt

# 3) Install Poppler (macOS example)
brew install poppler
```

Create a `.env` in the project root (do **not** commit this):

```
OPENAI_API_KEY=sk-...
USE_LLM_PARSER=true       # LLM parser on
USE_LLM_DEFAULT=true      # sessions start with LLM enabled
LOG_LEVEL=INFO            # use DEBUG for verbose apply/gap logs
USE_HEURISTIC_FALLBACK=false
```

> Ship a `./.env.example` and keep your real `.env` out of git.

---

## Run the server

```bash
# Dev script (hot reload, if provided)
./scripts/dev.sh

# Or run explicitly
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Quick smoke test (end-to-end)

```bash
./scripts/smoke_test.sh sample/sample_resume.pdf "Targeting Data Analyst roles"
```

What it does:
1. (Optional) Parse the PDF and log parser info
2. Start a session and print `SID`
3. Enable LLM for that `SID`
4. Fetch the next question
5. **Post a test patch list** (no LLM needed) to validate the update pipeline
6. Print a project snapshot

> In production you’ll post **natural text answers**; the server’s LLM converts them to the same patch format internally.

---

## Interactive drive (CLI)

```bash
./scripts/drive_cli.sh sample/sample_resume.pdf "Targeting Data Analyst roles"
```

- Parses the resume
- Starts a session
- Prompts you with the next question
- You answer in a single line (natural text)
- Server interprets and updates the profile
- Repeats (gaps shrink as fields get filled)

---

## Minimal API tour

- **Create session**  
  `POST /session/start`
  ```json
  {
    "resume_text": "…",
    "target_intro": "Targeting Data Analyst roles"
  }
  ```
  → returns `{ "session_id": "...", "profile": {...}, "next_question": {...} }`

- **Toggle LLM**  
  `POST /session/{sid}/config?use_llm=true|false`

- **Next question**  
  `GET /session/{sid}/next_question`

- **Answer (natural text OR direct patches JSON)**  
  `POST /session/{sid}/answer`
  ```json
  {
    "question_id": "<qid>",
    "answer_text": "I owned the data pipeline and model…"
  }
  ```
  or
  ```json
  {
    "question_id": "<qid>",
    "answer_text": "[{\"path\":\"projects[My Project].ownership\",\"value\":\"...\"}]"
  }
  ```
  → returns `{ applied_updates: [...], remaining_gaps: N, ... }`

- **Profile snapshot**  
  `GET /session/{sid}/profile`

- **Gaps**  
  `GET /session/{sid}/gaps` → `{ count, gaps: [...] }`

---

## RAG / prompts (conceptual)

- **Context**: Resume text, current profile (core + attributes), and recent Q&A lines.
- **Questioning**: Always one focused question at a time; prioritize high-value gaps (ownership, impact, stack depth, team context, recency).
- **Interpretation**: Convert free text answers into deterministic **patch lists** that target `projects[...]` or `skills[...]`. Unknown keys are allowed — they’ll be preserved under `attributes`.

**Business logic lives here:**
- `gap_finder.py`: *what* we ask next (and when a gap is considered filled).
- `updater.py`: *how* we apply/merge updates.
- `llm_agent.py`: LLM-driven question & interpretation (with optional RAG).

---

## Rubrics

- Stored in `rubrics/` (general + domain-specific).  
- The **general** rubric captures cross-role signals (ownership/impact/collab/complexity/quality/recency).  
- Domain rubrics (Data, Backend, PM, Design, …) layer on discipline-specific evidence.  
- You can evolve rubrics without locking the schema: new fields are accepted into `attributes`. When a field proves stable/useful, **promote it to core**.

---

## Troubleshooting

- **Core fields not updating but `attributes` has values**  
  - Ensure `Project` defines `ownership` and `collaboration` as core fields.
  - Ensure `updater.py` mirrors them: set core **and** `attributes[...]`.
  - Fully restart the server (clear `__pycache__` if needed).

- **Gap count not decreasing**  
  - `gap_finder.py` must treat **core OR attributes** as fulfilling a gap.
  - It’s common that other projects/skills still have gaps; list them:
    ```bash
    curl -s "$API/session/$SID/gaps"       | jq '.gaps | group_by(.gap_type) | map({type:.[0].gap_type, n:length})'
    ```

- **`pdftotext` not found**  
  - Install Poppler (`brew install poppler` on macOS).

- **Zsh prints `command not found: #`**  
  - You pasted comment lines into the shell; remove `# …` lines.

---

## Security & ops notes

- Never commit `.env` with secrets.  
- Use CI/secret stores to inject `OPENAI_API_KEY` in deployments.  
- Treat resumes as PII; apply retention, logging minimization, and encryption per your policy.

---

## Roadmap (short)

- Agent self-check (did we understand enough to stop asking?)
- Candidate embeddings (from the rich JSON)
- Action recommendations (what to ask/verify next)
- Expanded rubrics per role/discipline

---

**License**: PoC / internal use. Adapt as needed.
