from __future__ import annotations

"""
Updater
- Apply flexible {path, value} patches to the live profile object IN PLACE.
- Canonical project fields are stored on core attributes.
- Unknown fields are stored under `attributes` to avoid data loss.
- Supported bracket paths:
    projects[<index|title>].field(.subfield)
    skills[<name>].field(.subfield)
- Legacy paths supported:
    project.<field>:<title>
    skill.<field>:<name>
- Returns (applied_count, applied_patches) so the caller can report what changed.
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple

# Heuristic fallback is OFF by default to keep LLM-led behavior primary.
USE_HEURISTIC_FALLBACK = os.getenv("USE_HEURISTIC_FALLBACK", "0").lower() in (
    "1",
    "true",
)


# -----------------------------
# Generic helpers (no copies; mutate the live objects)
# -----------------------------
def _lower(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _get_projects_ref(profile: Any) -> List[Any]:
    """Return a live reference to profile.projects (list), creating if missing."""
    if isinstance(profile, dict):
        if "projects" not in profile or profile["projects"] is None:
            profile["projects"] = []
        return profile["projects"]
    projs = getattr(profile, "projects", None)
    if projs is None:
        setattr(profile, "projects", [])
        projs = getattr(profile, "projects")
    return projs


def _get_skills_ref(profile: Any) -> List[Any]:
    """Return a live reference to profile.skills (list), creating if missing."""
    if isinstance(profile, dict):
        if "skills" not in profile or profile["skills"] is None:
            profile["skills"] = []
        return profile["skills"]
    sks = getattr(profile, "skills", None)
    if sks is None:
        setattr(profile, "skills", [])
        sks = getattr(profile, "skills")
    return sks


def _project_title(p: Any) -> str:
    if isinstance(p, dict):
        return _lower(p.get("title"))
    return _lower(getattr(p, "title", None))


def _skill_name(s: Any) -> str:
    if isinstance(s, dict):
        return _lower(s.get("name"))
    return _lower(getattr(s, "name", None))


def _ensure_attrs(node: Any) -> Dict[str, Any]:
    """Ensure `attributes` dict exists and return it (works for dict or model)."""
    if isinstance(node, dict):
        if "attributes" not in node or node["attributes"] is None:
            node["attributes"] = {}
        return node["attributes"]
    cur = getattr(node, "attributes", None)
    if cur is None:
        setattr(node, "attributes", {})
        cur = getattr(node, "attributes")
    return cur


def _set(node: Any, key: str, value: Any) -> None:
    if isinstance(node, dict):
        node[key] = value
    else:
        # Only set known attributes on models; unknown must go into `attributes`.
        try:
            from pydantic import BaseModel  # optional import

            if isinstance(node, BaseModel):
                # pydantic v2: node.model_fields; v1: just try/except setattr
                fields = getattr(node, "model_fields", None)
                if isinstance(fields, dict) and key not in fields:
                    # unknown -> attributes
                    attrs = _ensure_attrs(node)
                    attrs[key] = value
                    return
        except Exception:
            pass
        setattr(node, key, value)


def _get(node: Any, key: str, default: Any = None) -> Any:
    if isinstance(node, dict):
        return node.get(key, default)
    return getattr(node, key, default)


def _to_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return [v]


# -----------------------------
# Find targets by ref
# -----------------------------
def _get_project_by_ref(profile: Any, ref: str) -> Optional[Any]:
    projs = _get_projects_ref(profile)
    if not projs:
        return None

    r = (ref or "").strip()
    if r.isdigit():
        i = int(r)
        if 0 <= i < len(projs):
            return projs[i]

    rl = _lower(r)
    best = None
    for p in projs:
        t = _project_title(p)
        if t == rl:
            return p
        if rl and rl in t and best is None:
            best = p
    return best


def _get_skill_by_ref(profile: Any, ref: str) -> Optional[Any]:
    sks = _get_skills_ref(profile)
    if not sks:
        return None
    rl = _lower(ref)
    for s in sks:
        if _skill_name(s) == rl:
            return s
    return None


# -----------------------------
# Assigners (project/skill fields)
# -----------------------------
def _merge_stack(cur: List[Any], incoming: Any) -> List[Any]:
    merged, seen = [], set()
    for x in list(cur or []) + _to_list(incoming):
        key = _lower(x) if isinstance(x, str) else str(x)
        if key and key not in seen:
            seen.add(key)
            merged.append(x)
    return merged


def _assign_project_field(prj: Any, field_path: str, value: Any) -> bool:
    """
    Canonical fields (stored on core):
      - stack/tech  -> stored as `stack` (merge, dedupe)
      - team_size   -> int
      - period      -> str
      - impact      -> dict or partial (impact.delta etc.)
    Everything else (unknown keys, including 'ownership'/'collaboration') goes under `attributes`.
    """
    parts = [p for p in (field_path or "").split(".") if p]
    if not parts:
        return False
    head = parts[0]

    # stack/tech → stack
    if head in {"stack", "tech"}:
        cur = _get(prj, "stack", []) or []
        _set(prj, "stack", _merge_stack(cur, value))
        return True

    if head == "team_size":
        try:
            _set(prj, "team_size", int(value))
            return True
        except Exception:
            return False

    if head == "period":
        _set(prj, "period", str(value))
        return True

    if head == "impact":
        cur = _get(prj, "impact", None)
        if cur is None:
            cur = {}
            _set(prj, "impact", cur)
        if isinstance(value, dict):
            if len(parts) == 2:
                cur[parts[1]] = value
            else:
                cur.update(value)
        else:
            cur["details"] = str(value)
        return True

    # Unknown → attributes (nested path preserved)
    attrs = _ensure_attrs(prj)
    cursor = attrs
    for p in parts[:-1]:
        nxt = cursor.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[p] = nxt
        cursor = nxt
    cursor[parts[-1]] = value
    return True


def _assign_skill_field(sk: Any, field_path: str, value: Any) -> bool:
    """
    Canonical skill fields:
      - depth/mode/frequency/last_used/role_alignment -> str
      - evidence -> list[str] (merged)
    Unknown fields go to `attributes`.
    """
    parts = [p for p in (field_path or "").split(".") if p]
    if not parts:
        return False
    head = parts[0]

    if head in {"depth", "mode", "frequency", "last_used", "role_alignment"}:
        _set(sk, head, str(value))
        return True

    if head == "evidence":
        cur = _get(sk, "evidence", []) or []
        inc = []
        for x in _to_list(value):
            xs = str(x).strip()
            if xs:
                inc.append(xs)
        # keep order, dedupe
        merged = list(dict.fromkeys(cur + inc))
        _set(sk, "evidence", merged)
        return True

    attrs = _ensure_attrs(sk)
    cursor = attrs
    for p in parts[:-1]:
        nxt = cursor.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[p] = nxt
        cursor = nxt
    cursor[parts[-1]] = value
    return True


# -----------------------------
# Public API
# -----------------------------
def apply_generic_updates(
    profile: Any, updates: List[Dict[str, Any]]
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Apply a list of patches IN PLACE.
    Supported:
      - "projects[<index or title>].field(.sub)"
      - "skills[<name>].field(.sub)"
      - "project.<field>:<title>"  (legacy)
      - "skill.<field>:<name>"    (legacy)
    Returns: (applied_count, applied_patches_list)
    """
    applied = 0
    applied_list: List[Dict[str, Any]] = []

    for u in updates or []:
        path = (u.get("path") or "").strip()
        val = u.get("value", None)
        if not path:
            continue

        # projects[ref].field
        m = re.match(r"^projects\[(.+?)\]\.(.+)$", path)
        if m:
            ref, fpath = m.group(1), m.group(2)
            prj = _get_project_by_ref(profile, ref)
            if prj is not None and _assign_project_field(prj, fpath, val):
                applied += 1
                applied_list.append({"path": path, "value": val})
            continue

        # skills[ref].field
        m = re.match(r"^skills\[(.+?)\]\.(.+)$", path)
        if m:
            ref, fpath = m.group(1), m.group(2)
            sk = _get_skill_by_ref(profile, ref)
            if sk is not None and _assign_skill_field(sk, fpath, val):
                applied += 1
                applied_list.append({"path": path, "value": val})
            continue

        # legacy: project.<field>:<title>
        if path.startswith("project."):
            try:
                head, title = path.split(":", 1)
                field = head.split(".", 1)[1]
            except Exception:
                continue
            prj = _get_project_by_ref(profile, title)
            if prj is not None and _assign_project_field(prj, field, val):
                applied += 1
                applied_list.append({"path": path, "value": val})
            continue

        # legacy: skill.<field>:<name>
        if path.startswith("skill."):
            try:
                head, name = path.split(":", 1)
                field = head.split(".", 1)[1]
            except Exception:
                continue
            sk = _get_skill_by_ref(profile, name)
            if sk is not None and _assign_skill_field(sk, field, val):
                applied += 1
                applied_list.append({"path": path, "value": val})
            continue

    return applied, applied_list


def apply_answer(
    profile: Any, gap_type: str, target: Optional[str], answer_text: str
) -> Any:
    """
    Optional heuristic fallback (OFF by default).
    Does nothing unless USE_HEURISTIC_FALLBACK is true.
    """
    if not USE_HEURISTIC_FALLBACK:
        return profile

    # Intentionally left minimal; if enabled, you could add small regex pickers here.
    return profile
