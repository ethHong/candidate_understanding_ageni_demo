# backend/app/repo.py
from __future__ import annotations
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
import json, uuid

from .models import SessionModel, QuestionModel, AnswerModel, ActionModel
from .schemas import Profile, ActionSchema


def _u() -> str:
    return str(uuid.uuid4())


# ---------- Profile coercion / serialization ----------


def coerce_profile(obj: Union[Profile, Dict[str, Any], Any]) -> Profile:
    if isinstance(obj, Profile):
        return obj
    if isinstance(obj, dict):
        return Profile(**obj)
    if hasattr(obj, "model_dump"):
        try:
            return Profile(**obj.model_dump())
        except Exception:
            pass
    # last resort: try to json -> dict -> Profile
    try:
        return Profile(**json.loads(json.dumps(obj)))
    except Exception:
        # return an empty shell rather than crash
        return Profile()


def profile_to_json(profile: Union[Profile, Dict[str, Any], Any]) -> str:
    p = coerce_profile(profile)
    return p.model_dump_json()


def profile_from_json(s: str) -> Profile:
    try:
        data = json.loads(s)
    except Exception:
        data = {}
    return Profile(**data)


# ---------- Sessions ----------


def create_session(
    db: Session,
    profile: Union[Profile, Dict[str, Any]],
    use_llm: bool = False,
    resume_text: str = "",
    target_intro: str = "",
) -> str:
    sid = _u()
    rec = SessionModel(
        id=sid,
        profile_json=profile_to_json(profile),
        use_llm=use_llm,
        resume_text=resume_text,
        target_intro=target_intro,
    )
    db.add(rec)
    db.commit()
    return sid


def get_session(db: Session, sid: str) -> Optional[SessionModel]:
    return db.get(SessionModel, sid)


def update_session_profile(
    db: Session, sid: str, profile: Union[Profile, Dict[str, Any]]
) -> bool:
    rec = get_session(db, sid)
    if not rec:
        return False
    rec.profile_json = profile_to_json(profile)
    db.add(rec)
    db.commit()
    return True


def set_session_llm(db: Session, sid: str, use_llm: bool) -> bool:
    rec = get_session(db, sid)
    if not rec:
        return False
    rec.use_llm = use_llm
    db.add(rec)
    db.commit()
    return True


# ---------- Q&A ----------


def add_question(
    db: Session, sid: str, gap_type: str, target: Optional[str], text: str
) -> str:
    qid = _u()
    db.add(
        QuestionModel(
            id=qid,
            session_id=sid,
            gap_type=gap_type,
            target=target,
            text=text,
            rationale=(
                f"Clarify {gap_type} for {target}" if target else f"Clarify {gap_type}"
            ),
        )
    )
    db.commit()
    return qid


def add_answer(db: Session, sid: str, question_id: str, answer_text: str) -> str:
    aid = _u()
    db.add(
        AnswerModel(
            id=aid,
            session_id=sid,
            question_id=question_id,
            text=answer_text,
        )
    )
    db.commit()
    return aid


def get_qa_tail(db: Session, sid: str, limit: int = 10) -> List[str]:
    stmt = (
        select(AnswerModel, QuestionModel)
        .join(QuestionModel, QuestionModel.id == AnswerModel.question_id)
        .where(AnswerModel.session_id == sid)
        .order_by(desc(AnswerModel.created_at))
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    out: List[str] = []
    for ans, q in rows:
        out.append(f"Q: {q.text}\nA: {ans.text}")
    return out


# ---------- Actions ----------


def add_actions(db: Session, sid: str, actions: List[ActionSchema]) -> int:
    n = 0
    for a in actions:
        db.add(
            ActionModel(
                id=_u(),
                session_id=sid,
                title=a.title,
                skill=a.skill,
                project_title=a.project_title,
                period=a.period,
                tech_stack_json=json.dumps(a.tech_stack or []),
                impact=a.impact,
                mode=a.mode,
                frequency=a.frequency,
            )
        )
        n += 1
    db.commit()
    return n


def list_actions(db: Session, sid: str) -> List[Dict[str, Any]]:
    rows = (
        db.execute(
            select(ActionModel)
            .where(ActionModel.session_id == sid)
            .order_by(desc(ActionModel.created_at))
        )
        .scalars()
        .all()
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r.id,
                "title": r.title,
                "skill": r.skill,
                "project_title": r.project_title,
                "period": r.period,
                "tech_stack": json.loads(r.tech_stack_json or "[]"),
                "impact": r.impact,
                "mode": r.mode,
                "frequency": r.frequency,
            }
        )
    return out
