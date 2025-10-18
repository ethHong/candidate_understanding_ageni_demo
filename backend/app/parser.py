# backend/app/parser.py
from __future__ import annotations
import os, json, re
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, ValidationError

# import your Pydantic schema types
from .schemas import Profile, Skill, Project

# ----------------------------
# Heuristic fallback (no LLM)
# ----------------------------

BASIC_SKILLS = {
    "sql",
    "python",
    "pyspark",
    "spark",
    "tableau",
    "power bi",
    "airflow",
    "aws",
    "gcp",
    "snowflake",
    "pytorch",
    "ml",
    "nlp",
    "experimentation",
    "a/b test",
    "ab test",
    "dashboards",
}

ACRONYMS = {
    "SQL",
    "AWS",
    "GCP",
    "NLP",
    "ML",
    "ETL",
    "BI",
    "DBT",
    "CI/CD",
    "A/B TEST",
    "AB TEST",
    "API",
    "NPS",
}


def _nice_skill_name(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return s
    u = s.upper()
    if u in ACRONYMS:
        return u
    # keep “Power BI” style
    s = s.replace("bi", "BI") if s.lower() == "power bi" else s
    return s[:1].upper() + s[1:]


def _find_skills(text: str) -> List[Skill]:
    t = text.lower()
    found: List[Skill] = []
    for s in BASIC_SKILLS:
        if s in t:
            found.append(
                Skill(
                    name=_nice_skill_name(s),
                    depth="intermediate",
                    evidence=[],
                    confidence=0.7,
                )
            )
    # minimal set if nothing matched
    if not found:
        found = [Skill(name="SQL"), Skill(name="Python")]
    # de-dupe by name
    dedup = {}
    for sk in found:
        dedup[sk.name.lower()] = sk
    return list(dedup.values())


_HDR_LINE = re.compile(r"(.+?)\s+—\s+(.+)$")  # “Company — Role”


def _find_projects(text: str) -> List[Project]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    titles: List[str] = []
    for ln in lines:
        if _HDR_LINE.search(ln) and 8 < len(ln) < 160:
            titles.append(ln)
    if not titles:
        titles = ["Resume Project"]
    out: List[Project] = []
    for t in titles[:8]:
        out.append(Project(title=t, stack=[], actions=[], confidence=0.55))
    return out


def _fallback_profile(text: str, target_intro: Optional[str]) -> Profile:
    return Profile(
        core={"target_role": None, "domains": []},
        skills=_find_skills(text),
        projects=_find_projects(text),
        competencies={
            "technical_depth": 0.7,
            "analytics_rigor": 0.7,
            "product_sense": 0.7,
            "communication": 0.7,
        },
        fit_notes="Draft from text."
        + (f" Intro: {target_intro}" if target_intro else ""),
    )


# ----------------------------
# LLM helpers
# ----------------------------


def _llm_enabled() -> bool:
    return os.getenv("USE_LLM_PARSER", "false").lower() == "true" and bool(
        os.getenv("OPENAI_API_KEY")
    )


def _model_name() -> str:
    return os.getenv("LLM_MODEL", "gpt-4o-mini")


def _extract_first_json(s: str) -> Optional[dict]:
    """
    Be forgiving: grab the first {...} that parses.
    """
    if not s:
        return None
    # quick fence: if it's already a pure JSON object
    s_strip = s.strip()
    if s_strip.startswith("{") and s_strip.endswith("}"):
        try:
            return json.loads(s_strip)
        except Exception:
            pass
    # else scan
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    blob = s[start : end + 1]
    try:
        return json.loads(blob)
    except Exception:
        return None


def _norm_conf(v: Any, default: float = 0.7) -> float:
    try:
        x = float(v)
        if x > 1.0:  # LLM may return 0..100
            x = x / 100.0
        if x < 0:
            x = 0.0
        if x > 1:
            x = 1.0
        return x
    except Exception:
        return default


def _norm_skill(sk: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(sk or {})
    out["name"] = _nice_skill_name(out.get("name", ""))
    out["confidence"] = _norm_conf(out.get("confidence", 0.7))
    # depth sanity
    if out.get("depth") not in {"basic", "intermediate", "advanced"}:
        out["depth"] = out.get("depth") or "intermediate"
    # mode sanity
    if out.get("mode") not in {None, "coded", "led", "both"}:
        out["mode"] = None
    # frequency sanity
    if out.get("frequency") not in {None, "daily", "weekly", "monthly", "rare"}:
        out["frequency"] = None
    return out


def _norm_project(pr: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(pr or {})
    out["title"] = (out.get("title") or "").strip() or "Experience"
    out["company"] = (out.get("company") or None) or None
    out["role"] = (out.get("role") or None) or None
    out["period"] = (out.get("period") or None) or None
    # normalize stack
    stack = out.get("stack") or []
    out["stack"] = [
        _nice_skill_name(s) for s in stack if isinstance(s, str) and s.strip()
    ]
    # normalize actions
    acts = out.get("actions") or []
    out["actions"] = [a.strip() for a in acts if isinstance(a, str) and a.strip()]
    # impact
    imp = out.get("impact")
    if isinstance(imp, dict):
        out["impact"] = {
            "metric": imp.get("metric"),
            "delta": imp.get("delta"),
            "details": imp.get("details"),
        }
    elif imp is None:
        out["impact"] = None
    else:
        out["impact"] = None
    # team_size
    ts = out.get("team_size")
    if isinstance(ts, (int, float)):
        try:
            out["team_size"] = int(ts)
        except Exception:
            out["team_size"] = None
    else:
        out["team_size"] = None
    # confidence 0..1
    out["confidence"] = _norm_conf(out.get("confidence", 0.7))
    return out


def _normalize_profile_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    d = dict(d or {})
    d.setdefault("core", {})
    d.setdefault("skills", [])
    d.setdefault("projects", [])
    d.setdefault("competencies", {})
    d.setdefault("fit_notes", "Parsed by LLM.")

    # skills dedupe by name (case-insensitive)
    seen = {}
    norm_skills = []
    for sk in d["skills"]:
        if not isinstance(sk, dict):
            continue
        skn = _norm_skill(sk)
        key = skn["name"].lower()
        if key in seen:
            # merge evidence if present
            if skn.get("evidence"):
                seen[key]["evidence"] = (seen[key].get("evidence") or []) + list(
                    skn["evidence"]
                )
            # keep max confidence
            seen[key]["confidence"] = max(
                seen[key].get("confidence", 0.0), skn["confidence"]
            )
        else:
            seen[key] = skn
    norm_skills = list(seen.values())

    # projects normalize and trim
    norm_projects = []
    for pr in d["projects"]:
        if isinstance(pr, dict):
            norm_projects.append(_norm_project(pr))
    # keep at most 20
    norm_projects = norm_projects[:20]

    d["skills"] = norm_skills
    d["projects"] = norm_projects
    return d


# ----------------------------
# LLM parsing
# ----------------------------


def _llm_parse_with_openai(
    resume_text: str, target_intro: Optional[str]
) -> Optional[Profile]:
    """
    Use OpenAI Chat Completions with JSON response. Return Profile or None if failed.
    """
    try:
        from openai import OpenAI
    except Exception:
        return None

    api = OpenAI()
    model = _model_name()

    sys_prompt = (
        "You are a recruiter-grade resume parser.\n"
        "Return STRICT JSON with these keys:\n"
        "core: {target_role?: string|null, yoe?: number|null, domains?: string[]}\n"
        "skills: [{name: string, depth?: 'basic'|'intermediate'|'advanced', evidence?: string[], confidence?: number, mode?: 'coded'|'led'|'both'|null, role_alignment?: string|null, frequency?: 'daily'|'weekly'|'monthly'|'rare'|null, last_used?: string|null}]\n"
        "projects: [{title: string, role?: string|null, company?: string|null, period?: string|null, stack?: string[], actions?: string[], impact?: {metric?: string|null, delta?: string|number|null, details?: string|null}|null, team_size?: number|null, confidence?: number}]\n"
        "competencies: {technical_depth?: number, analytics_rigor?: number, product_sense?: number, communication?: number}\n"
        "fit_notes: string\n\n"
        "INCLUDE entries from ALL of these sections if present:\n"
        "• Professional Experience / Work Experience (each role becomes a project: {company, role, period, actions})\n"
        "• Projects / Research (normal projects)\n"
        "• Education (each degree as a project with role: 'Education', company=school, period, stack from core tools/coursework, actions from thesis/capstone)\n\n"
        "Rules: deduplicate; keep actions concise and verb-led; avoid hallucinations; if uncertain leave fields null."
    )

    user_prompt = (
        f"TARGET INTRO (optional): {target_intro or ''}\n"
        f"RESUME (first 15k chars):\n{resume_text[:15000]}"
    )

    try:
        resp = api.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = resp.choices[0].message.content or ""
        raw = json.loads(content)
        norm = _normalize_profile_dict(raw)
        return Profile(**norm)
    except Exception:
        return None


def _llm_parse_with_langchain(
    resume_text: str, target_intro: Optional[str]
) -> Optional[Profile]:
    """
    Fallback to LangChain ChatOpenAI if available.
    """
    try:
        from langchain_openai import ChatOpenAI
    except Exception:
        return None

    llm = ChatOpenAI(model=_model_name(), temperature=0)
    sys_prompt = (
        "You are a recruiter-grade resume parser.\n"
        "Return STRICT JSON with these keys:\n"
        "core: {target_role?: string|null, yoe?: number|null, domains?: string[]}\n"
        "skills: [{name: string, depth?: 'basic'|'intermediate'|'advanced', evidence?: string[], confidence?: number, mode?: 'coded'|'led'|'both'|null, role_alignment?: string|null, frequency?: 'daily'|'weekly'|'monthly'|'rare'|null, last_used?: string|null}]\n"
        "projects: [{title: string, role?: string|null, company?: string|null, period?: string|null, stack?: string[], actions?: string[], impact?: {metric?: string|null, delta?: string|number|null, details?: string|null}|null, team_size?: number|null, confidence?: number}]\n"
        "competencies: {technical_depth?: number, analytics_rigor?: number, product_sense?: number, communication?: number}\n"
        "fit_notes: string\n\n"
        "INCLUDE entries from ALL of these sections if present:\n"
        "• Professional Experience / Work Experience (each role becomes a project)\n"
        "• Projects / Research\n"
        "• Education (degree entries become projects with role 'Education')\n"
        "Rules: deduplicate; action verbs; avoid hallucinations; leave null when unsure."
    )
    user_prompt = (
        f"TARGET INTRO (optional): {target_intro or ''}\n"
        f"RESUME (first 15k chars):\n{resume_text[:15000]}"
    )
    try:
        r = llm.invoke(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        content = getattr(r, "content", "") or ""
        data = _extract_first_json(content)
        if not data:
            return None
        norm = _normalize_profile_dict(data)
        return Profile(**norm)
    except Exception:
        return None


# ----------------------------
# Public API
# ----------------------------


def build_profile_from_resume(resume_text: str, target_intro: Optional[str]) -> Profile:
    """
    LLM → normalized Profile; fallback to heuristics if disabled or on error.
    """
    if _llm_enabled():
        p = _llm_parse_with_openai(resume_text, target_intro)
        if p:
            return p
        p = _llm_parse_with_langchain(resume_text, target_intro)
        if p:
            return p
    # fallback
    return _fallback_profile(resume_text, target_intro)


def parse_actions_from_profile(profile: Profile) -> List[dict]:
    """
    Convert project actions → Action rows with project context.
    """
    out: List[dict] = []
    for pr in profile.projects:
        acts = pr.actions or []
        for a in acts:
            if not isinstance(a, str) or not a.strip():
                continue
            out.append(
                {
                    "title": a.strip(),
                    "project_title": pr.title,
                    "project_role": pr.role,
                    "project_company": pr.company,
                    "frequency": "weekly",
                }
            )
    return out
