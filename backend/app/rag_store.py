# backend/app/rag_store.py
from __future__ import annotations

import os
import glob
import json
import re
from typing import List, Dict, Optional

try:
    import yaml
except Exception:
    yaml = None


_DEFAULT_RUBRICS = {
    "skill_depth": [
        "Hands-on vs. leading: what did you personally build/operate?",
        "Recency (YYYY-MM) and frequency (daily/weekly/monthly).",
        "Frameworks/libraries/tools and why they were chosen.",
        "Scale/complexity (rows/GB/users/latency) and bottlenecks handled.",
        "Debugging/optimization stories that show depth.",
    ],
    "project_impact": [
        "Metric + baseline → delta (percent/time/money/quality/volume).",
        "Evaluation method (A/B, backtest, benchmarks) and sample size.",
        "Business/user outcome in plain language.",
        "Scope (stakeholders, users, revenue, datasets).",
        "Repeatability/automation that sustained the impact.",
    ],
    "ownership": [
        "What did you own end-to-end? What decisions did you make?",
        "Stakeholders; mentoring/coordination; reliability/maintenance.",
    ],
    "stack_details": [
        "Concrete tools/services and where each fits in the workflow.",
        "Interfacing systems (DBs, warehouses, APIs, schedulers, infra).",
    ],
    "skill_recency": [
        "When last used (YYYY-MM) and how often currently.",
        "In which project/context; recency vs. seniority trade-offs.",
    ],
    "target_role": [
        "Target roles and strengths mapped to them.",
        "Role-fit narrative: top 2–3 proof points for that role.",
    ],
}


def load_rubric_chunks_for(dimension: str, role: Optional[str] = None) -> List[str]:
    texts: List[str] = []
    texts += _load_from_dir(_new_dir(), dimension, role)
    texts += _load_from_dir(_legacy_dir(), dimension, role)
    if not texts:
        texts = list(_DEFAULT_RUBRICS.get(dimension, []))

    seen = set()
    out: List[str] = []
    for t in texts:
        t = (t or "").strip()
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append(t)
        if len(out) >= 16:
            break
    return out


# ----------------- UTIL -----------------
def _here():
    return os.path.dirname(__file__)


def _new_dir():
    return os.path.join(_here(), "rubrics")


def _legacy_dir():
    # LEGACY: backend/rubric/*
    return os.path.join(os.path.dirname(_here()), "rubric")


_DIM_HEAD_RE = {
    "skill_depth": re.compile(r"^\s{0,3}#{1,6}.*skill[\s_-]*depth", re.I),
    "project_impact": re.compile(r"^\s{0,3}#{1,6}.*project[\s_-]*impact", re.I),
    "ownership": re.compile(r"^\s{0,3}#{1,6}.*owner", re.I),
    "stack_details": re.compile(r"^\s{0,3}#{1,6}.*stack|tool", re.I),
    "skill_recency": re.compile(r"^\s{0,3}#{1,6}.*recency|frequency", re.I),
    "target_role": re.compile(r"^\s{0,3}#{1,6}.*target.*role", re.I),
}


def _role_slug(role: Optional[str]) -> Optional[str]:
    if not role:
        return None
    s = re.sub(r"[^a-zA-Z]+", " ", role).strip().lower()
    mapping = {
        "data analyst": "analyst",
        "analyst": "analyst",
        "analytics": "analyst",
        "data scientist": "ds",
        "scientist": "ds",
        "engineer": "engineer",
        "software engineer": "engineer",
        "product manager": "pm",
        "pm": "pm",
        "designer": "designer",
        "marketing": "marketing",
        "operations": "ops",
        "operations manager": "ops",
        "research": "research",
    }
    for k, v in mapping.items():
        if k in s:
            return v
    tok = s.split()[0] if s else None
    return tok or None


def _load_from_dir(dir_path: str, dimension: str, role: Optional[str]) -> List[str]:
    if not dir_path or not os.path.isdir(dir_path):
        return []
    files = glob.glob(os.path.join(dir_path, "*"))
    if not files:
        return []
    dim = (dimension or "").strip().lower()
    role_slug = _role_slug(role)

    general_hits: List[str] = []
    role_hits: List[str] = []

    for p in files:
        ext = os.path.splitext(p)[1].lower()
        fname = os.path.basename(p).lower()

        if "general" in fname or fname.startswith(dim) or dim in fname:
            general_hits += _extract_texts(p, dim)

        if role_slug and role_slug in fname:
            role_hits += _extract_texts(p, dim)

    return general_hits + role_hits


def _extract_texts(path: str, dim: str) -> List[str]:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".yml", ".yaml") and yaml:
            with open(path, "r", encoding="utf-8") as fh:
                doc = yaml.safe_load(fh)
            return _from_yaml(doc, dim)
        elif ext in (".json",):
            with open(path, "r", encoding="utf-8") as fh:
                doc = json.load(fh)
            return _from_json(doc, dim)
        else:  # .md/.txt
            with open(path, "r", encoding="utf-8") as fh:
                txt = fh.read()
            return _from_md(txt, dim)
    except Exception:
        return []


def _from_yaml(doc: Dict, dim: str) -> List[str]:
    if not isinstance(doc, dict):
        return []
    out: List[str] = []
    if dim in doc and isinstance(doc[dim], list):
        out += [str(x) for x in doc[dim] if isinstance(x, (str, int, float))]
    dims = doc.get("dimensions")
    if isinstance(dims, list):
        for it in dims:
            if isinstance(it, dict) and it.get("id") == dim:
                bullets = it.get("bullets") or it.get("ask_for") or it.get("notes")
                if isinstance(bullets, list):
                    out += [str(x) for x in bullets if isinstance(x, (str, int, float))]
    node = doc.get(dim)
    if isinstance(node, dict):
        for v in node.values():
            if isinstance(v, list):
                out += [str(x) for x in v if isinstance(x, (str, int, float))]
    return out


def _from_json(doc: Dict, dim: str) -> List[str]:
    if not isinstance(doc, dict):
        return []
    out: List[str] = []
    if dim in doc and isinstance(doc[dim], list):
        out += [str(x) for x in doc[dim] if isinstance(x, (str, int, float))]
    if "dimensions" in doc and isinstance(doc["dimensions"], dict):
        node = doc["dimensions"].get(dim)
        if isinstance(node, list):
            out += [str(x) for x in node if isinstance(x, (str, int, float))]
    return out


def _from_md(txt: str, dim: str) -> List[str]:
    lines = [ln.rstrip() for ln in txt.splitlines()]
    if not lines:
        return []
    head_re = _DIM_HEAD_RE.get(dim)
    if head_re:
        capture = False
        bucket: List[str] = []
        for ln in lines:
            if head_re.search(ln):
                capture = True
                continue
            if capture and ln.startswith("#"):
                break
            if capture and ln.strip():
                bucket.append(ln.strip("- ").strip())
        if bucket:
            return [b for b in bucket if b]
    # 못 찾으면 앞 단락들을 짧게
    paras = [p.strip() for p in re.split(r"\n{2,}", txt) if p.strip()]
    out: List[str] = []
    for p in paras:
        out.append(p[:240])
        if len(out) >= 8:
            break
    return out
