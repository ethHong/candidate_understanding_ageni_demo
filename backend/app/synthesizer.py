from __future__ import annotations
from .schemas import Profile

def synthesize_summary(profile: Profile) -> str:
    name = profile.core.name or "This candidate"
    role = profile.core.target_role or "Data/Product role"
    top_skills = ", ".join([s.name for s in sorted(profile.skills, key=lambda x: x.confidence, reverse=True)[:5]]) or "generalist skills"
    notes = profile.fit_notes or ""
    comps = profile.competencies
    comp_txt = f"technical depth {comps.technical_depth:.2f}, analytics rigor {comps.analytics_rigor:.2f}, product sense {comps.product_sense:.2f}, communication {comps.communication:.2f}."
    proj_lines = []
    for p in profile.projects[:3]:
        imp = ""
        if p.impact and p.impact.get("metric"):
            delta = p.impact.get("delta", "")
            imp = f" → impact: {p.impact['metric']} {delta}".strip()
        proj_lines.append(f"- {p.title}{imp}")
    projects_block = "\n".join(proj_lines) if proj_lines else "- Projects to be clarified."

    summary = (
        f"{name} targets a {role}. Key strengths: {top_skills}.\n"
        f"Competencies: {comp_txt}\n"
        f"Projects:\n{projects_block}\n"
        f"Notes: {notes}"
    )
    return summary
