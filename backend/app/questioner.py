from __future__ import annotations
from typing import Dict
from .schemas import Question

_TEMPLATES = {
    "skill_depth": "On {target}: would you say your level is basic, intermediate, or advanced? How do you typically use it?",
    "project_impact": 'For the project "{target}": what changed as a result (metrics, % improvement, cost/time saved)?',
    "ownership": 'In "{target}": which parts did you personally own versus collaborate on?',
    "team_size": 'Roughly how many people worked on "{target}" and what functions (e.g., 1 PM, 2 DEs, 1 analyst)?',
    "stack_details": 'For "{target}": which tools and tech did you actually use week-to-week?',
    "target_role": "What role are you targeting now, and which strengths do you want to emphasize?",
}


def make_question(gap: Dict) -> Question:
    qid = __import__("uuid").uuid4().hex
    gtype = gap["gap_type"]
    target = gap.get("target")
    text = _TEMPLATES.get(
        gtype, "Could you share more details about this area?"
    ).format(target=target)
    rationale = f"Clarify {gtype} for {target}"
    return Question(
        id=qid, text=text, gap_type=gtype, target=target, rationale=rationale
    )
