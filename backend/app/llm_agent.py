# backend/app/llm_agent.py
from __future__ import annotations


import os
import json
import re
from typing import List, Dict, Optional, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from .rag_store import load_rubric_chunks_for


# -----------------------------
# LLM INSTANCE
# -----------------------------
def llm() -> ChatOpenAI:

    return ChatOpenAI(model=os.getenv("LLM_MODEL", "gpt-4o-mini"), temperature=0.2)


# -----------------------------
# JSON PARSING
# -----------------------------
_JSON_RE = re.compile(r"(\{.*\}|\[.*\])", re.DOTALL)


def _json_from_text(txt: str) -> Optional[Any]:
    if not txt:
        return None

    try:
        return json.loads(txt)
    except Exception:
        pass

    m = _JSON_RE.search(txt)
    if not m:
        return None
    snippet = m.group(1)
    try:
        return json.loads(snippet)
    except Exception:
        return None


def _compact_profile_snapshot(profile) -> Dict[str, Any]:

    def _skills(p):
        try:
            return [getattr(s, "name", "") for s in getattr(p, "skills", []) or []]
        except Exception:
            return [
                s.get("name") for s in (p.get("skills") or []) if isinstance(s, dict)
            ]

    def _projects(p):
        try:
            return [getattr(x, "title", "") for x in getattr(p, "projects", []) or []]
        except Exception:
            return [
                x.get("title") for x in (p.get("projects") or []) if isinstance(x, dict)
            ]

    target_role = None
    try:
        target_role = getattr(getattr(profile, "core", None), "target_role", None)
    except Exception:
        if isinstance(profile, dict):
            target_role = (profile.get("core") or {}).get("target_role")

    return {
        "skills": _skills(profile),
        "projects": _projects(profile),
        "target_role": target_role,
    }


def _extract_role(profile, intro: str) -> Optional[str]:

    snap = _compact_profile_snapshot(profile)
    if snap.get("target_role"):
        return snap["target_role"]
    txt = (intro or "").lower()
    for key in [
        "analyst",
        "engineer",
        "scientist",
        "product manager",
        "pm",
        "designer",
        "marketing",
        "operations",
        "research",
    ]:
        if key in txt:
            return key
    return None


# -----------------------------
# Question Prompt
# -----------------------------
Q_SYS = """You are a technical recruiter. Ask ONE next question to maximize information gain.
Use the rubric to decide which specific attributes to ask.
Return STRICT JSON only:
{"text":"<one concise question>", "gap_type":"<gap type>", "target":"<entity name>", "ask_for":["field","field2"]}
No extra commentary, no markdown.
"""


# -----------------------------
# Patch Prompt
# -----------------------------
U_SYS = """You convert a free-form candidate answer into PATCHES that update the profile.
Return STRICT JSON ONLY: a LIST of {"path":"...","value":...}.

Use bracket paths (recommended):
- projects[<title or index>].<field>[.subfield]
- skills[<name>].<field>

Examples:
[
  {"path":"projects[Business Insight Analyst – Intern].ownership","value":"I owned ingestion & modeling"},
  {"path":"projects[0].stack","value":["MS SQL Server","PySpark","Power BI"]},
  {"path":"skills[Python].evidence","value":"Built PySpark pipelines weekly"}
]
Do not add any commentary.
"""


# -----------------------------
# Create Question
# -----------------------------
def draft_question_llm_with_rag(
    sid: str,
    profile,
    gaps: List[Dict],
    resume_text: str,
    target_intro: str,
    qa_lines: List[str],
) -> Optional[Dict]:
    if not gaps:
        return None

    gap = gaps[0]
    role = _extract_role(profile, target_intro)
    rubric_ctx = load_rubric_chunks_for(gap.get("gap_type"), role=role) or []

    ctx = {
        "session_id": sid,
        "gap": gap,
        "recent_qa": qa_lines[-6:] if qa_lines else [],
        "profile_snapshot": _compact_profile_snapshot(profile),
        "target_intro": (target_intro or "")[:1000],
        "rubric": rubric_ctx[:12],  # 과도한 길이 방지
    }

    msgs = [
        SystemMessage(content=Q_SYS),
        HumanMessage(content=json.dumps(ctx, ensure_ascii=False)),
    ]
    res = llm().invoke(msgs)
    data = _json_from_text(getattr(res, "content", "") or "")

    if not isinstance(data, dict):
        return None

    return {
        "text": (data.get("text") or gap.get("text") or "").strip()
        or f"Could you share more details about {gap.get('target') or gap.get('gap_type')}?",
        "gap_type": data.get("gap_type") or gap.get("gap_type"),
        "target": data.get("target") or gap.get("target"),
        "ask_for": data.get("ask_for") or gap.get("prompt_hint") or None,
    }


# -----------------------------
# Interpret Response
# -----------------------------
def interpret_answer_llm_with_rag(
    sid: str, profile, gap_type: str, target: str, answer_text: str, qa_lines: List[str]
) -> Optional[List[Dict[str, Any]]]:

    role = _extract_role(profile, "")
    rubric_ctx = load_rubric_chunks_for(gap_type, role=role) or []

    ctx = {
        "session_id": sid,
        "gap_type": gap_type,
        "target": target,
        "recent_qa": qa_lines[-6:] if qa_lines else [],
        "profile_snapshot": _compact_profile_snapshot(profile),
        "answer": (answer_text or "")[:4000],
        "rubric": rubric_ctx[:12],
    }

    msgs = [
        SystemMessage(content=U_SYS),
        HumanMessage(
            content=f"CONTEXT(JSON): {json.dumps(ctx, ensure_ascii=False)[:6000]}"
        ),
    ]
    try:
        res = llm().invoke(msgs)
        raw = getattr(res, "content", "") or ""
    except Exception:
        return None

    def _force_json(t: str):
        j = _json_from_text(t)
        return j

    data = _force_json(raw)
    if data is None:
        return None

    def _to_patches(obj) -> List[Dict[str, Any]]:

        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict) and "path" in x]

        if isinstance(obj, dict):
            # {patches:[...]} or {updates:[...]} 케이스
            for k in ("patches", "updates"):
                if isinstance(obj.get(k), list):
                    return [x for x in obj[k] if isinstance(x, dict) and "path" in x]

            # {target:"...", ownership:"...", team_size:...} → 평탄화
            tgt = obj.get("target") or target or ""
            flat = []
            for k, v in obj.items():
                if k == "target":
                    continue
                flat.append({"path": f"projects[{tgt}].{k}", "value": v})
            return flat

        return []

    patches = _to_patches(data)

    def _shorten(v):
        if isinstance(v, str) and len(v) > 500:
            return v[:497] + "..."
        return v

    normed = []
    for p in patches:
        path = (p.get("path") or "").strip()
        if not path:
            continue
        val = _shorten(p.get("value"))

        if any(path.endswith(suf) for suf in (".tech", ".stack")) and isinstance(
            val, str
        ):
            val = [x.strip() for x in val.split(",") if x.strip()]
        normed.append({"path": path, "value": val})

    return normed or []
