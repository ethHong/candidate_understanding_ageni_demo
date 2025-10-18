# COMES — Conversational Profile MVP
_A lightweight, LLM-optional system that parses a resume, finds profile gaps, asks clarifying questions, applies answers, and synthesizes a candidate profile._

**Version:** 0.2.x  
**Audience:** you + any collaborator who needs to understand, run, or extend this codebase.  
**Scope:** structure, roles of files, request/response flow, environment flags, where to tweak LLM prompts/agents, DB layout, and copy‑pasteable CLI flows for testing.

---

## 1) System Overview

### What it does
1. **Parse** resume text (PDF or plain text) into a structured `Profile`.
2. **Compute gaps** in that profile (missing target role, weak skill evidence, unknown last_used, project impact, etc.).
3. **Ask questions** to close gaps (LLM‑generated or heuristic fallback).
4. **Apply answers** to update the profile (LLM interpreter + heuristic safety net).
5. **Synthesize** a final narrative summary (optional).

### High-level architecture
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

### Prereqs
- Python 3.10+
- `pip install -r requirements.txt`
- Optional LLM features: set **`OPENAI_API_KEY`** and the feature flags below

### Key environment flags (in `.env`)
```
# Turn on LLM parsing for /parse_resume and /parse_resume_file
USE_LLM_PARSER=true

# Turn on LLM question/answer behavior for each new session by default
USE_LLM_DEFAULT=true

# OpenAI config (use your model; defaults exist in code)
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

---

## 2) Data Model (Pydantic schemas)

```python
# schemas.Profile (simplified)
core: {
  name: str|None,
  target_role: str|None,
  yoe: float|int|None,
  domains: list[str] = []
}
skills: list[{
  name: str,
  depth: "basic"|"intermediate"|"advanced"|None,
  evidence: list[str] = [],
  confidence: float|int|None,
  mode: "coded"|"led"|"both"|None,
  role_alignment: str|None,
  frequency: "daily"|"weekly"|"monthly"|"rare"|None,
  last_used: str|None
}]
projects: list[{
  title: str,
  role: str|None,
  company: str|None,
  period: str|None,
  stack: list[str] = [],
  actions: list[str] = [],
  impact: {metric: str|None, delta: str|int|None} | None,
  team_size: int|None,
  confidence: float|int|None
}]
competencies: {technical_depth, analytics_rigor, product_sense, communication}
fit_notes: str
```

DB tables (SQLite):
- `sessions(id, created_at, updated_at, use_llm, profile_json, resume_text, target_intro)`
- `questions(id, session_id, created_at, text, gap_type, target)`
- `answers(id, session_id, question_id, created_at, text)`
- `actions(id, session_id, created_at, title, project_title, project_role, project_company, frequency)`  
  (Optional: populated from parsed projects’ actions or later LLM extraction)

---

## 3) Module-by-module

### `main.py` — API surface & orchestration
Endpoints:
- `GET /health` – basic liveness
- `POST /parse_resume` – parse from string text
- `POST /parse_resume_file` – parse from uploaded file (PDF or text)
- `POST /session/start` – create session; stores profile/resume/intro; returns first question (if any)
- `GET /session/{sid}/next_question` – returns next gap question (LLM or fallback)
- `POST /session/{sid}/answer` – records answer, applies updates, returns `applied_updates` + `remaining_gaps`
- `GET /session/{sid}/profile` – current profile JSON
- `POST /session/{sid}/synthesize` – final narrative (if you built it)
- `POST /session/{sid}/config?use_llm=true|false` – enable/disable LLM for Q&A
- `GET /session/{sid}/gaps` – snapshot of gaps (count + list)
- `POST /session/{sid}/bootstrap_actions` – seed `actions` table using `parse_actions_from_profile`

Where to tune behavior in `main.py`:
- **LLM question** path: `draft_question_llm_with_rag(...)` (if LLM enabled); fallback is `questioner.make_question`
- **LLM answer interpreter** path: `interpret_answer_llm_with_rag(...)` → `apply_generic_updates(...)`
- **Heuristic fallback** always runs: `updater.apply_answer(...)`
- Profiles are persisted via `repo.update_session_profile(...)`

### `parser.py` — resume → `Profile`
- Tries **LLM parser** when `USE_LLM_PARSER=true` and `OPENAI_API_KEY` is set.
  - Prompt ensures it returns **strict JSON** shaped like `Profile` keys.
  - Merges **Professional Experience** and **Projects/Research** into the single `projects[]` list (you can keep a `source:"experience|project|education"` tag if needed).
- Falls back to simple heuristics when LLM is unavailable.
- `parse_actions_from_profile(profile)` converts `projects[].actions` into `Action` rows (for `/bootstrap_actions`).

**Where to customize LLM parsing**  
Edit the **system prompt** and **USER prompt assembly** inside `build_profile_from_resume()`. Add fields like `source`, fine‑tune how periods/companies are extracted, or enforce confidence ranges.

### `gap_finder.py` — compute “what to ask next”
- Produces a list of gap dicts: `{"gap_type": "...","target": "...","label": "..."}`
- Examples: `target_role`, `skill_mode`, `skill_last_used`, `actions_for_skill`, `project_impact`.
- You can change priorities, thresholds, and which fields trigger questions.

### `llm_agent.py` (optional)
- `draft_question_llm_with_rag(...)` turns current gaps + QA tail into **contextual questions**.
- `interpret_answer_llm_with_rag(...)` transforms free‑text answers into **structured updates** (e.g., set `skills[Sql].mode="coded"`, add an `action`, set `projects[i].impact`).
- Add your **RAG** retrieval here (e.g., vector store over previous QAs or resume chunks), or more rigorous extraction prompts.
- Tunables: both prompts; the “update schema” you expect the model to emit.

### `updater.py`
- `apply_generic_updates(profile, updates)` – consumes structured updates from LLM path.
- `apply_answer(profile, gap_type, target, answer_text)` – simple heuristic safety net (e.g., append evidence to the matching skill).

### `questioner.py`
- Heuristic, last‑resort question suggestions when LLM questioner is off or fails.

### `synthesizer.py` (optional)
- Converts `Profile` to 1–2 paragraph summary for UI/export. Edit prompt here to add tone/length controls.

### `text_extract.py`
- `pdf_bytes_to_text(data: bytes) -> str`: robust PDF → text using `pypdf`, with fallback to UTF‑8 decode.

### `db.py`, `models.py`, `repo.py`
- SQLAlchemy setup + helpers for CRUD (`create_session`, `add_question`, `add_answer`, `update_session_profile`, `list_actions`, `add_actions`, `get_qa_tail`, …).

### `schemas.py`
- All FastAPI request/response and core domain models (Pydantic v2).  
- If you add fields, update both `schemas.py` and any logic reading/writing them (parser, updater, gap_finder, etc.).

---

## 4) End-to-end request flow

1. **Upload resume** → `POST /parse_resume_file`  
   - `text_extract.pdf_bytes_to_text` gets raw text  
   - `parser.build_profile_from_resume` turns it into `Profile` (LLM or heuristics)  
   - Returns a **draft profile**, not saved yet

2. **Start a session** → `POST /session/start`  
   - Stores `resume_text`, `target_intro`, and profile in DB  
   - Computes gaps and **returns the first question**

3. **Get next question** → `GET /session/{sid}/next_question`  
   - Uses LLM questioner (if enabled) or `questioner.make_question`

4. **Answer** → `POST /session/{sid}/answer`  
   - Adds to `answers`  
   - Runs LLM interpreter (if enabled) and heuristic fallback  
   - **Saves updated profile** and returns `applied_updates` + `remaining_gaps`

5. **Inspect** → `GET /session/{sid}/profile` and `GET /session/{sid}/gaps`  
   - Use these in UI to show progress

6. **(Optional) Synthesize** → `POST /session/{sid}/synthesize`

---

## 5) CLI: Copy‑paste flows for testing

> All commands assume `API="http://127.0.0.1:8000"` and `PDF="sample/sample_resume.pdf"`

### A. Quick parse + peek (checks LLM parser)
```bash
API="http://127.0.0.1:8000"
PDF="sample/sample_resume.pdf"

curl -s -F "file=@${PDF}" -F "target_intro=Targeting Data Analyst roles" \
  "$API/parse_resume_file" \
| jq '.notes,
     {projects: (.profile_draft.projects[:6] | map({title,company,role,period}))},
     {skills: (.profile_draft.skills[:10] | map({name,depth,last_used,frequency}))}'
```

### B. Start a session, enable LLM, ask/answer once, show profile/gaps
```bash
API="http://127.0.0.1:8000"
PDF="sample/sample_resume.pdf"
TXT=$(pdftotext -layout "$PDF" - | tr -d '\f')

SID=$(jq -n --arg rt "$TXT" --arg ti "Targeting DA roles" \
  '{resume_text:$rt, target_intro:$ti}' \
  | curl -s -X POST "$API/session/start" -H "Content-Type: application/json" -d @- \
  | jq -r '.session_id')

curl -s -X POST "$API/session/$SID/config?use_llm=true" | jq
curl -s "$API/session/$SID/gaps" | jq '.count'

Q=$(curl -s "$API/session/$SID/next_question")
echo "$Q" | jq
QID=$(echo "$Q" | jq -r '.question.id')

ANS='At LA Clippers (Jun–Sep 2025) I used MS SQL Server daily to analyze ~40M events, built CTE pipelines & Power BI views; impact: +6.8% attach, +12% MoM revenue; hands-on 3x/week; last used 2025-09.'

curl -s -X POST "$API/session/$SID/answer" -H "Content-Type: application/json" \
  -d "$(jq -n --arg q "$QID" --arg a "$ANS" '{question_id:$q, answer_text:$a}')" \
| jq '{checked, applied_updates, remaining_gaps, notes}'

curl -s "$API/session/$SID/profile" \
| jq '.profile | {core, skills: ( .skills | map({name,mode,last_used,frequency,ev:(.evidence|length)}) ), projects: ( .projects | map({title,company,role,period,impact}) ) }'
```

### C. Full flow with computed diff (drop‑in script)
Use the included script (or create it) at `scripts/flow_demo_with_diff.sh`:
```bash
chmod +x scripts/flow_demo_with_diff.sh
./scripts/flow_demo_with_diff.sh sample/sample_resume.pdf "Targeting Data Analyst roles"
```
What it prints:
- Parsed draft snapshot
- New session id, LLM enabled
- Current gap count
- Next question
- You enter an answer (or use the sample)
- Server’s `applied_updates` (from LLM) + **computed diff before/after** (works even if heuristic updated the profile)
- New gap count and profile snapshot

### D. Seed + inspect actions (optional)
```bash
SID="<your-session-id>"
curl -s -X POST "$API/session/$SID/bootstrap_actions" | jq
curl -s "$API/session/$SID/gaps" | jq
```

---

## 6) Where & how to tune prompts / agents

### LLM Resume Parser → `parser.py::build_profile_from_resume`
- **System prompt**: controls required JSON shape and rules (dedupe, concise actions, avoid hallucination).
- **User prompt**: include `target_intro` and resume text; you can add headings like “PROFESSIONAL EXPERIENCE / PROJECTS / EDUCATION” to bias extraction.
- Consider adding a field like `"source": "experience|project|education"` on each `project` item for later UI grouping.

### LLM Questioner → `llm_agent.py::draft_question_llm_with_rag`
- Adjust how the next question is chosen from gaps.
- Add retrieval over resume/QA history (vector store) to ground the question in context.

### LLM Answer Interpreter → `llm_agent.py::interpret_answer_llm_with_rag`
- Define the **update schema** you want the model to emit (e.g., set `skills[i].mode`, `skills[i].last_used`, append `projects[j].actions`, set `projects[j].impact`).
- In `updater.apply_generic_updates` map these updates into the `Profile` structure.

> Tip: keep prompts short, provide 1‑2 **examples** of desired structured updates, and **validate** the JSON on the server before applying.

---

## 7) Troubleshooting

- **Parser returns “Resume Project” only**
  - Ensure `.env` has `USE_LLM_PARSER=true` and `OPENAI_API_KEY` exists
  - Check logs for LangChain warnings; upgrade to pydantic v2 APIs if needed
  - Confirm the resume text length (some PDFs extract poorly; try another extractor if necessary)

- **`applied_updates` is `null`**
  - LLM interpreter is disabled or couldn’t produce structured updates. Heuristic fallback still updated the profile.
  - Use the **diff CLI** script to see *what actually changed*.

- **DB migration issues**
  - Use the debug migration endpoint (if present) or manually remove the old SQLite file when schema changes are incompatible.
  - Verify columns: `answers.text` must exist if you added it; re‑create DB with `Base.metadata.create_all(bind=engine)` on startup.

- **Repeated questions about the same gap**
  - Confirm `gap_finder` removes a gap once the relevant fields are populated.
  - Check that `apply_answer` or `apply_generic_updates` actually sets the corresponding field (e.g., `skills[].mode` is not still `null`).

---

## 8) Roadmap Ideas

- Add `"source"` to `projects[]`: `"experience" | "project" | "education"` for better grouping.
- Build **RAG** over resume sections and recent QAs.
- Persist **diff history** per answer (`before_profile`, `after_profile`) for auditability.
- Export **profile → resume bullets** and **job‑fit analysis**.
- UI: question queue + progress bar; inline “what changed” after each answer.

---

## 9) Minimal Runbook

1. `pip install -r requirements.txt`
2. Create `.env`:
   ```
   USE_LLM_PARSER=true
   USE_LLM_DEFAULT=true
   OPENAI_API_KEY=sk-...
   LLM_MODEL=gpt-4o-mini
   ```
3. `uvicorn app.main:app --reload` (from `backend/` directory)
4. Run any CLI snippet above (A/B/C/D).

---

## 10) Reference: Endpoint Cheatsheet

```
POST /parse_resume          {resume_text, target_intro} → {profile_draft}
POST /parse_resume_file     multipart(file, target_intro) → {profile_draft}
POST /session/start         {resume_text, target_intro} → {session_id, profile, next_question?}
GET  /session/{sid}/next_question → {question, remaining_gaps}
POST /session/{sid}/answer  {question_id, answer_text} → {checked, applied_updates?, remaining_gaps, notes}
GET  /session/{sid}/profile → {profile}
GET  /session/{sid}/gaps    → {count, gaps[]}
POST /session/{sid}/config?use_llm=true|false → {session_id, use_llm}
POST /session/{sid}/synthesize → {summary_text}
POST /session/{sid}/bootstrap_actions → {added, skipped}
```

---

**That’s it.** This document is safe to share with collaborators or paste into ChatGPT to continue iterating on prompts, gaps, and update logic.
