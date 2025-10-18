from __future__ import annotations

"""
Gap finder
- Compute a list of gaps the agent should ask about next.
- A gap is considered "filled" if the information exists either on core fields
  or in the `attributes` mirror (free-form storage).
"""

from typing import Any, Dict, List, Optional


def _lower(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _as_dict(node: Any) -> Dict:
    if isinstance(node, dict):
        return node
    try:
        # pydantic v2
        return node.model_dump()
    except Exception:
        try:
            # pydantic v1
            return node.dict()
        except Exception:
            return dict(node or {})


def _get_attrs(n: Any) -> Dict:
    if isinstance(n, dict):
        return n.get("attributes") or {}
    try:
        return getattr(n, "attributes", None) or {}
    except Exception:
        return {}


def _has_value(*vals) -> bool:
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and v.strip():
            return True
        if isinstance(v, (int, float)) and v != 0:
            return True
        if isinstance(v, (list, dict)) and len(v) > 0:
            return True
    return False


def _project_title(p: Any) -> str:
    if isinstance(p, dict):
        return p.get("title") or ""
    return getattr(p, "title", "") or ""


def compute_gaps(profile: Any, actions: Optional[List[Dict]] = None) -> List[Dict]:
    """
    Returns a list of gap dicts:
      {"gap_type": "<type>", "target": "<entity>", "rationale": "..."}
    Rules consider BOTH core fields and `attributes` mirror as fulfilling info.
    """
    p = profile
    try:
        projs = getattr(p, "projects", None)
        skills = getattr(p, "skills", None)
        core = getattr(p, "core", None)
    except Exception:
        d = _as_dict(p)
        projs = d.get("projects", [])
        skills = d.get("skills", [])
        core = d.get("core", {})

    gaps: List[Dict] = []

    # ---- project-centric gaps ----
    for pr in projs or []:
        title = _project_title(pr)
        attrs = _get_attrs(pr)

        # ownership
        own_core = (
            getattr(pr, "ownership", None)
            if not isinstance(pr, dict)
            else pr.get("ownership")
        )
        own_attr = attrs.get("ownership")
        if not _has_value(own_core, own_attr):
            gaps.append(
                {
                    "gap_type": "ownership",
                    "target": title,
                    "rationale": f"Clarify ownership for {title}",
                }
            )

        # stack_details
        stack_core = (
            getattr(pr, "stack", None) if not isinstance(pr, dict) else pr.get("stack")
        )
        stack_attr = attrs.get("stack") or attrs.get("tech")
        if not _has_value(stack_core, stack_attr):
            gaps.append(
                {
                    "gap_type": "stack_details",
                    "target": title,
                    "rationale": f"Collect stack/tools for {title}",
                }
            )

        # project_impact
        imp_core = (
            getattr(pr, "impact", None)
            if not isinstance(pr, dict)
            else pr.get("impact")
        )
        imp_attr = attrs.get("impact")

        # consider filled if any of delta/metric/details exists either side
        def _impact_filled(v) -> bool:
            if isinstance(v, dict):
                return _has_value(v.get("delta"), v.get("metric"), v.get("details"))
            return _has_value(v)

        if not (_impact_filled(imp_core) or _impact_filled(imp_attr)):
            gaps.append(
                {
                    "gap_type": "project_impact",
                    "target": title,
                    "rationale": f"Clarify impact for {title}",
                }
            )

        # team_size (optional rule; drop if you don't want it)
        team_core = (
            getattr(pr, "team_size", None)
            if not isinstance(pr, dict)
            else pr.get("team_size")
        )
        team_attr = attrs.get("team_size")
        if not _has_value(team_core, team_attr):
            gaps.append(
                {
                    "gap_type": "team_context",
                    "target": title,
                    "rationale": f"Team size/context for {title}",
                }
            )

    # ---- skills-centric gaps (very light) ----
    for sk in skills or []:
        name = (
            sk.get("name") if isinstance(sk, dict) else getattr(sk, "name", "")
        ) or ""
        if not name:
            continue
        attrs = _get_attrs(sk)
        depth = (
            sk.get("depth") if isinstance(sk, dict) else getattr(sk, "depth", None)
        ) or attrs.get("depth")
        last_used = (
            sk.get("last_used")
            if isinstance(sk, dict)
            else getattr(sk, "last_used", None)
        ) or attrs.get("last_used")
        if not _has_value(depth):
            gaps.append(
                {
                    "gap_type": "skill_depth",
                    "target": name,
                    "rationale": f"Clarify depth for skill {name}",
                }
            )
        if not _has_value(last_used):
            gaps.append(
                {
                    "gap_type": "skill_recency",
                    "target": name,
                    "rationale": f"Last used / frequency for skill {name}",
                }
            )

    # Optionally: use `actions` to suppress some gaps if recurring work already implies depth/recency.
    # (left as-is to avoid changing your pipeline semantics)

    return gaps
