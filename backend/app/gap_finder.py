# backend/app/gap_finder.py
from __future__ import annotations
from typing import Any, Dict, List, Optional


# Small utilities (kept local to avoid import cycles)
def _as_dict(obj: Any) -> dict:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    try:
        return vars(obj)
    except Exception:
        return dict(obj) if obj is not None else {}


def _get(d: dict, path: str, default=None):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key, default)
    return cur


def _lower(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _skill_has_any_evidence(sk: dict) -> bool:
    ev = sk.get("evidence") or []
    return isinstance(ev, list) and any(isinstance(x, str) and x.strip() for x in ev)


def _skill_recent_or_freq(sk: dict) -> bool:
    last = sk.get("last_used") or ""
    freq = sk.get("frequency") or ""
    return bool(last or freq)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def compute_gaps(
    profile_in: Any,
    actions: Optional[List[dict]] = None,
    links: Optional[List[dict]] = None,  # reserved for future use
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Compute gaps from profile (+ optional actions/links).
    Tolerant to extra kwargs from callers.
    """
    profile = _as_dict(profile_in)
    gaps: List[Dict[str, Any]] = []

    core = _get(profile, "core", {}) or {}
    skills = _get(profile, "skills", []) or []
    projects = _get(profile, "projects", []) or []

    # ---- 0) Target role missing --------------------------------------------
    if not _lower(core.get("target_role")):
        gaps.append(
            {"gap_type": "target_role", "label": "Clarify target role", "target": None}
        )

    # ---- 1) Skill-depth / actions / recency --------------------------------
    for s in skills:
        sk = _lower(s.get("name"))
        if not sk:
            continue

        # 1a) Hands-on vs leading
        if not s.get("mode"):
            gaps.append(
                {"gap_type": "skill_mode", "label": "Hands-on vs leading", "target": sk}
            )

        # 1b) Concrete action for skill
        if not _skill_has_any_evidence(s):
            gaps.append(
                {
                    "gap_type": "actions_for_skill",
                    "label": "Concrete actions for skill",
                    "target": sk,
                }
            )

        # 1c) Recency/frequency unknown
        if not _skill_recent_or_freq(s):
            gaps.append(
                {
                    "gap_type": "skill_recency",
                    "label": "When/how often used",
                    "target": sk,
                }
            )

    # ---- 2) Projects: impact & ownership & stack ----------------------------
    for p in projects:
        title = _lower(p.get("title"))
        if not title:
            continue
        imp = p.get("impact")
        ownership = p.get("ownership")
        tech = p.get("tech") or p.get("stack") or []

        # Impact missing or underspecified
        need_impact = False
        if not imp:
            need_impact = True
        elif isinstance(imp, dict) and not (imp.get("metric") and imp.get("delta")):
            need_impact = True

        if need_impact:
            gaps.append(
                {
                    "gap_type": "project_impact",
                    "label": "Project impact",
                    "target": p.get("title"),
                }
            )

        # Ownership
        if not ownership:
            gaps.append(
                {
                    "gap_type": "ownership",
                    "label": "Ownership/role depth",
                    "target": p.get("title"),
                }
            )

        # Stack details (optional enhancement)
        if not tech:
            gaps.append(
                {
                    "gap_type": "stack_details",
                    "label": "Actual tools/stack used",
                    "target": p.get("title"),
                }
            )

    # simple priority: keep current order; server picks gaps[0] first
    return gaps
