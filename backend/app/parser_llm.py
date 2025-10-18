# backend/app/parser_llm.py
from __future__ import annotations
import json, os, re
from typing import Optional, List, Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from .schemas import Profile  # pydantic model

_SYSTEM = """You are a structured resume extractor for hiring.
Return STRICT JSON. No prose. Target schema:
{
  "core": {"name": str|null, "target_role": str|null, "yoe": float|null, "domains": [str]},
  "skills": [{"name": str, "depth": "basic|intermediate|advanced|unknown", "evidence": [str]}],
  "projects": [
    {
      "title": str,
      "role": str|null,
      "period": str|null,
      "company": str|null,
      "stack": [str],
      "actions": [str],
      "impact": {"metric": str|null, "delta": float|null}|null,
      "team_size": int|null
    }
  ],
  "competencies": {"technical_depth": float, "analytics_rigor": float, "product_sense": float, "communication": float},
  "fit_notes": str
}
Rules:
- Only treat job/project sections as projects (NOT education/summary).
- Keep actions concrete (what was built/changed), include metrics when present.
- stack is concise tooling/tech; don’t invent.
- If uncertain, use nulls/empty arrays.
"""


def _llm() -> ChatOpenAI:
    return ChatOpenAI(model=os.getenv("LLM_MODEL", "gpt-4o-mini"), temperature=0)


def _strip_code_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s.split("\n", 1)[1] if "\n" in s else s
    return s


def llm_build_profile(resume_text: str, target_intro: Optional[str]) -> Profile:
    user = f"""RESUME_TEXT: {resume_text[:50000]}
    TARGET_INTRO (optional):
{target_intro or ""}
Please output ONLY the JSON for the schema."""
    resp = _llm().invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=user)])
    raw = _strip_code_fences(resp.content or "")
    data = json.loads(raw)

    # Defensive defaults
    comps = data.get("competencies") or {
        "technical_depth": 0.7,
        "analytics_rigor": 0.7,
        "product_sense": 0.7,
        "communication": 0.7,
    }
    return Profile(
        core=data.get("core")
        or {"name": None, "target_role": None, "yoe": None, "domains": []},
        skills=data.get("skills") or [],
        projects=data.get("projects") or [],
        competencies=comps,
        fit_notes=data.get("fit_notes") or "LLM parsed.",
    )
