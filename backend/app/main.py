# backend/app/main.py
from __future__ import annotations
from typing import Optional, List, Dict, Any
import os
import json

from fastapi import FastAPI, UploadFile, File, Form, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .db import SessionLocal, engine, Base
from .models import QuestionModel
from .schemas import (
    ParseRequest,
    ParseResponse,
    HealthResponse,
    SessionStartRequest,
    SessionStartResponse,
    NextQuestionResponse,
    AnswerRequest,
    AnswerApplyResponse,
    ProfileResponse,
    SynthesisResponse,
    Question as QuestionSchema,
    Profile,
    ActionSchema,
    CheckedGap,
)
from .repo import (
    create_session,
    get_session,
    update_session_profile,
    set_session_llm,
    add_question,
    add_answer,
    profile_from_json,
    get_qa_tail,
    add_actions,
    list_actions,
    coerce_profile,
)

from dotenv import load_dotenv

load_dotenv()  # Load .env so OPENAI_API_KEY / USE_LLM_PARSER etc. are visible

from .text_extract import pdf_bytes_to_text  # Robust PDF→text

# LLM agent (optional)
try:
    from .llm_agent import draft_question_llm_with_rag, interpret_answer_llm_with_rag
except Exception:
    draft_question_llm_with_rag = None
    interpret_answer_llm_with_rag = None

# Simple fallback questioner
try:
    from .questioner import make_question
except Exception:

    def make_question(gap):
        class _Q:
            def __init__(self, text, gap_type, target):
                self.text = text
                self.gap_type = gap_type
                self.target = target

        t = gap.get("target") or ""
        gt = gap.get("gap_type", "general")
        return _Q(f"Could you tell me more about '{t}' to clarify {gt}?", gt, t)


# Updater (LLM patches + optional heuristics)
try:
    from .updater import apply_answer, apply_generic_updates
except Exception:

    def apply_answer(profile, gap_type, target, answer_text):
        # Minimal fallback: append as skill evidence when target matches skill name
        p = coerce_profile(profile).model_dump()
        for s in p.get("skills", []):
            if s.get("name", "").lower() == (target or "").lower():
                ev = s.get("evidence", [])
                ev.append(answer_text)
                s["evidence"] = ev
        return Profile(**p)

    def apply_generic_updates(profile, updates):
        # No-op fallback returns (count, applied_list)
        return (0, [])


# Summarizer (optional)
try:
    from .synthesizer import synthesize_summary
except Exception:

    def synthesize_summary(profile: Profile) -> str:
        return "Summary not implemented."


# Parser (resume → initial profile + actions)
try:
    from .parser import build_profile_from_resume, parse_actions_from_profile
except Exception:

    def build_profile_from_resume(
        resume_text: str, target_intro: Optional[str]
    ) -> Profile:
        # Very naive fallback profile
        return Profile(
            core={"target_role": None, "domains": []},
            skills=[{"name": "SQL"}, {"name": "Python"}],
            projects=[{"title": "Resume Project"}],
            fit_notes="Draft from text.",
        )

    def parse_actions_from_profile(profile: Profile) -> List[dict]:
        acts = []
        for pr in profile.projects:
            for a in pr.actions:
                acts.append(
                    {"title": a, "project_title": pr.title, "frequency": "weekly"}
                )
        return acts


from .gap_finder import compute_gaps

app = FastAPI(title="COMES — Conversational Profile MVP", version="0.2.2")


@app.on_event("startup")
def on_startup():
    # Ensure DB schema is created on startup
    Base.metadata.create_all(bind=engine)


# Open CORS in dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@app.post("/parse_resume", response_model=ParseResponse)
async def parse_resume(req: ParseRequest):
    profile = build_profile_from_resume(req.resume_text, req.target_intro)
    return ParseResponse(profile_draft=profile, notes="Draft profile synthesized.")


@app.post("/parse_resume_file", response_model=ParseResponse)
async def parse_resume_file(
    file: UploadFile = File(...), target_intro: Optional[str] = Form(None)
):
    # Accept either PDF (bytes→text) or plain text uploads
    raw = await file.read()
    fname = (file.filename or "").lower()
    ctype = (file.content_type or "").lower()

    if fname.endswith(".pdf") or "pdf" in ctype:
        text = pdf_bytes_to_text(raw)
        src = "pdf-bytes→text"
    else:
        text = raw.decode("utf-8", errors="ignore")
        src = "plain-text"

    profile = build_profile_from_resume(text, target_intro)
    notes = (
        f"Draft profile from {src} (len={len(text)}) for {file.filename}. "
        f"USE_LLM_PARSER={os.getenv('USE_LLM_PARSER')} "
        f"OPENAI_KEY={'yes' if os.getenv('OPENAI_API_KEY') else 'no'}"
    )
    return ParseResponse(profile_draft=profile, notes=notes)


@app.post("/session/start", response_model=SessionStartResponse)
async def session_start(req: SessionStartRequest):
    # Build initial profile then create a session record
    profile = build_profile_from_resume(req.resume_text, req.target_intro)
    use_llm_default = os.getenv("USE_LLM_DEFAULT", "false").lower() == "true"

    with SessionLocal() as db:
        sid = create_session(
            db,
            profile,
            use_llm=use_llm_default,
            resume_text=req.resume_text or "",
            target_intro=req.target_intro or "",
        )

        # Prime first question
        gaps = compute_gaps(profile)
        q_obj: Optional[QuestionSchema] = None
        if gaps:
            q_text, gap_type, target = None, None, None
            if (
                use_llm_default
                and draft_question_llm_with_rag
                and os.getenv("OPENAI_API_KEY")
            ):
                llm_q = draft_question_llm_with_rag(
                    sid=sid,
                    profile=profile,
                    gaps=gaps,
                    resume_text=req.resume_text or "",
                    target_intro=req.target_intro or "",
                    qa_lines=[],
                )
                if llm_q:
                    q_text, gap_type, target = (
                        llm_q["text"],
                        llm_q["gap_type"],
                        llm_q.get("target"),
                    )

            if not q_text:
                qq = make_question(gaps[0])
                q_text, gap_type, target = qq.text, qq.gap_type, qq.target

            qid = add_question(db, sid, gap_type, target, q_text)
            q_obj = QuestionSchema(
                id=qid,
                text=q_text,
                gap_type=gap_type,
                target=target,
                rationale=f"Clarify {gap_type} for {target}",
            )

        return SessionStartResponse(
            session_id=sid, profile=profile, next_question=q_obj
        )


@app.get("/session/{sid}/next_question", response_model=NextQuestionResponse)
async def next_question(sid: str):
    # Produce the next high-value question based on remaining gaps
    with SessionLocal() as db:
        rec = get_session(db, sid)
        if not rec:
            raise HTTPException(status_code=404, detail="Session not found")

        profile = profile_from_json(rec.profile_json)
        actions = []
        try:
            actions = list_actions(db, sid) or []
        except Exception:
            actions = []

        gaps = compute_gaps(profile, actions=actions)
        if not gaps:
            return NextQuestionResponse(session_id=sid, question=None, remaining_gaps=0)

        q_text, gap_type, target = None, None, None
        if rec.use_llm and draft_question_llm_with_rag and os.getenv("OPENAI_API_KEY"):
            qa_lines = get_qa_tail(db, sid, limit=10)
            llm_q = draft_question_llm_with_rag(
                sid=sid,
                profile=profile,
                gaps=gaps,
                resume_text=rec.resume_text or "",
                target_intro=rec.target_intro or "",
                qa_lines=qa_lines,
            )
            if llm_q:
                q_text, gap_type, target = (
                    llm_q["text"],
                    llm_q["gap_type"],
                    llm_q.get("target"),
                )

        if not q_text:
            qq = make_question(gaps[0])
            q_text, gap_type, target = qq.text, qq.gap_type, qq.target

        qid = add_question(db, sid, gap_type, target, q_text)
        q_obj = QuestionSchema(
            id=qid,
            text=q_text,
            gap_type=gap_type,
            target=target,
            rationale=f"Clarify {gap_type} for {target}",
        )
        remaining = max(0, len(gaps) - 1)
        return NextQuestionResponse(
            session_id=sid, question=q_obj, remaining_gaps=remaining
        )


# ---------- helpers to parse patches directly from user answer ----------
def _json_from_text(txt: str) -> Optional[Any]:
    """Best-effort JSON loader for either a list or an object."""
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        return None


def _to_patches(obj: Any, default_target: Optional[str]) -> List[Dict[str, Any]]:
    """Normalize various shapes into a patch list: [{path, value}]"""
    if obj is None:
        return []

    # Already a list of patches
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict) and "path" in x]

    # Object with embedded patch list
    if isinstance(obj, dict):
        for k in ("patches", "updates"):
            if isinstance(obj.get(k), list):
                return [x for x in obj[k] if isinstance(x, dict) and "path" in x]

        # Flat object -> assume project target and flatten
        tgt = obj.get("target") or default_target or ""
        patches = []
        for k, v in obj.items():
            if k == "target":
                continue
            patches.append({"path": f"projects[{tgt}].{k}", "value": v})
        return patches

    return []


@app.post("/session/{sid}/answer", response_model=AnswerApplyResponse)
async def answer_apply(sid: str, payload: AnswerRequest):
    # Apply the user's answer: direct JSON patches → updater; otherwise LLM → patches → updater
    with SessionLocal() as db:
        rec = get_session(db, sid)
        if not rec:
            raise HTTPException(status_code=404, detail="Session not found")

        qrec = (
            db.query(QuestionModel)
            .filter(
                QuestionModel.id == payload.question_id,
                QuestionModel.session_id == sid,
            )
            .first()
        )
        if not qrec:
            raise HTTPException(
                status_code=400, detail="Invalid question_id for this session"
            )

        # Persist raw answer for audit trail
        add_answer(db, sid, payload.question_id, payload.answer_text)

        profile = profile_from_json(rec.profile_json)
        checked = CheckedGap(gap_type=qrec.gap_type, label=None, target=qrec.target)

        applied_updates: List[dict] = []
        applied_count_total = 0

        # (A) Try to parse direct JSON patches from answer_text (no LLM needed)
        direct_obj = _json_from_text(payload.answer_text)
        direct_patches = (
            _to_patches(direct_obj, default_target=qrec.target)
            if direct_obj is not None
            else []
        )
        if direct_patches:
            count, applied_list = apply_generic_updates(profile, direct_patches)
            applied_count_total += count
            if applied_list:
                applied_updates.extend(applied_list)
            profile = coerce_profile(profile)

        # (B) If nothing applied yet and LLM is enabled, interpret answer to patches
        if (
            applied_count_total == 0
            and rec.use_llm
            and interpret_answer_llm_with_rag
            and os.getenv("OPENAI_API_KEY")
        ):
            qa_lines = get_qa_tail(db, sid, limit=10)
            try:
                llm_updates = (
                    interpret_answer_llm_with_rag(
                        sid=sid,
                        profile=profile,
                        gap_type=qrec.gap_type,
                        target=qrec.target,
                        answer_text=payload.answer_text,
                        qa_lines=qa_lines,
                    )
                    or []
                )
                if llm_updates:
                    count, applied_list = apply_generic_updates(profile, llm_updates)
                    applied_count_total += count
                    if applied_list:
                        applied_updates.extend(applied_list)
                    profile = coerce_profile(profile)
            except Exception:
                # Swallow LLM errors but continue with heuristic fallback if needed
                pass

        # (C) Heuristic fallback ONLY if nothing was applied by A or B
        if applied_count_total == 0:
            profile = apply_answer(
                profile, qrec.gap_type, qrec.target, payload.answer_text
            )
            profile = coerce_profile(profile)

        # Persist updated profile
        update_session_profile(db, sid, profile)

        # Recompute remaining gaps
        actions = []
        try:
            actions = list_actions(db, sid) or []
        except Exception:
            actions = []
        remaining = len(compute_gaps(profile, actions=actions))

        return AnswerApplyResponse(
            session_id=sid,
            profile=profile,
            notes="Answer applied.",
            checked=checked,
            applied_updates=applied_updates or None,
            remaining_gaps=remaining,
        )


@app.get("/session/{sid}/profile", response_model=ProfileResponse)
async def get_profile_route(sid: str):
    # Return the latest stored profile
    with SessionLocal() as db:
        rec = get_session(db, sid)
        if not rec:
            raise HTTPException(status_code=404, detail="Session not found")
        return ProfileResponse(
            session_id=sid, profile=profile_from_json(rec.profile_json)
        )


@app.post("/session/{sid}/synthesize", response_model=SynthesisResponse)
async def synthesize_route(sid: str):
    # Summarize the profile (optional feature)
    with SessionLocal() as db:
        rec = get_session(db, sid)
        if not rec:
            raise HTTPException(status_code=404, detail="Session not found")
        txt = synthesize_summary(profile_from_json(rec.profile_json))
        return SynthesisResponse(session_id=sid, summary_text=txt)


@app.post("/session/{sid}/config")
async def set_config(sid: str, use_llm: bool):
    # Toggle LLM usage for this session
    with SessionLocal() as db:
        ok = set_session_llm(db, sid, use_llm)
        if not ok:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"session_id": sid, "use_llm": use_llm}


@app.get("/session/{sid}/gaps")
def gaps_summary(sid: str):
    # Expose gap count and raw list
    with SessionLocal() as db:
        rec = get_session(db, sid)
        if not rec:
            raise HTTPException(status_code=404, detail="Session not found")
        profile = profile_from_json(rec.profile_json)
        actions = []
        try:
            actions = list_actions(db, sid) or []
        except Exception:
            actions = []
        gaps = compute_gaps(profile, actions=actions)
        return {"session_id": sid, "count": len(gaps), "gaps": gaps}


def _coerce_freq(s: Optional[str]) -> str:
    # Normalize frequency values into one of: daily/weekly/monthly/rare
    if not s:
        return "weekly"
    s = s.strip().lower()
    if s in {"daily", "weekly", "monthly", "rare"}:
        return s
    if "ongoing" in s or "regular" in s or "often" in s or "frequent" in s:
        return "weekly"
    if "day" in s:
        return "daily"
    if "month" in s:
        return "monthly"
    if "rare" in s or "occas" in s or "sporadic" in s or "infrequent" in s:
        return "rare"
    return "weekly"


@app.post("/session/{sid}/bootstrap_actions")
def bootstrap_actions(sid: str, payload: dict = Body(default=None)):
    # Seed action items either from payload or by parsing the current profile
    with SessionLocal() as db:
        rec = get_session(db, sid)
        if not rec:
            raise HTTPException(status_code=404, detail="Session not found")

        acts = []
        if (
            payload
            and isinstance(payload, dict)
            and isinstance(payload.get("actions"), list)
        ):
            acts = payload["actions"]
        else:
            try:
                prof = profile_from_json(rec.profile_json)
                acts = parse_actions_from_profile(prof) or []
            except Exception:
                acts = []

        cleaned: List[ActionSchema] = []
        for a in acts:
            if not isinstance(a, dict):
                continue
            a = a.copy()
            a["frequency"] = _coerce_freq(a.get("frequency"))
            try:
                cleaned.append(ActionSchema(**a))
            except Exception:
                continue

        added = 0
        if cleaned:
            added = add_actions(db, sid, cleaned)

        return {"session_id": sid, "added": added, "skipped": max(0, len(acts) - added)}
