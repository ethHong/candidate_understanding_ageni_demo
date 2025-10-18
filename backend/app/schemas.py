# backend/app/schemas.py
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, field_validator


# ---------- Core profile structures ----------
# Provide a "LooseModel" that allows unknown fields (pydantic v2 and v1 compatible)
try:
    # pydantic v2
    from pydantic import ConfigDict

    class LooseModel(BaseModel):
        # Allow extra keys without raising; they can be read/written if needed
        model_config = ConfigDict(extra="allow")

except Exception:
    # pydantic v1 fallback
    class LooseModel(BaseModel):
        class Config:
            extra = "allow"


class CoreInfo(BaseModel):
    name: Optional[str] = None
    target_role: Optional[str] = None
    yoe: Optional[int] = None
    domains: List[str] = []


class Skill(BaseModel):
    name: str
    depth: Optional[Literal["basic", "intermediate", "advanced"]] = "intermediate"
    evidence: List[str] = []
    confidence: float = 0.7
    # richer skill signals
    mode: Optional[Literal["coded", "led"]] = None
    role_alignment: Optional[str] = None
    frequency: Optional[str] = None
    last_used: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class Impact(BaseModel):
    metric: Optional[str] = None
    delta: Optional[str] = None
    details: Optional[str] = None


# In schemas.py — replace the Project class with this definition.

from typing import List, Optional, Dict, Any
from pydantic import Field


class Project(LooseModel):
    """Project entity with loose extra-field policy.
    Known/core fields live here; everything else may live under `attributes`.
    """

    title: str
    role: Optional[str] = None
    company: Optional[str] = None
    period: Optional[str] = None
    team_size: Optional[int] = None
    stack: List[str] = Field(default_factory=list)
    impact: Dict[str, Any] = Field(default_factory=dict)
    actions: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)

    # Core mirrors for frequently used free-form keys
    ownership: Optional[str] = None
    collaboration: Optional[str] = None


class Competencies(BaseModel):
    technical_depth: float = 0.7
    analytics_rigor: float = 0.7
    product_sense: float = 0.7
    communication: float = 0.7


class Profile(BaseModel):
    core: CoreInfo = Field(default_factory=CoreInfo)
    skills: List[Skill] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    competencies: Competencies = Field(default_factory=Competencies)
    fit_notes: Optional[str] = None


# ---------- Questions / Answers ----------


class Question(BaseModel):
    id: str
    text: str
    gap_type: str
    target: Optional[str] = None
    rationale: Optional[str] = None


class CheckedGap(BaseModel):
    gap_type: str
    label: Optional[str] = None
    target: Optional[str] = None


# ---------- Actions (structured, persisted) ----------

AllowedFrequency = Literal["daily", "weekly", "monthly", "rare"]


class Action(BaseModel):
    title: str
    skill: Optional[str] = None
    project_title: Optional[str] = None
    period: Optional[str] = None
    tech_stack: List[str] = []
    impact: Optional[str] = None
    mode: Optional[Literal["coded", "led"]] = None
    frequency: AllowedFrequency = "weekly"

    @field_validator("frequency", mode="before")
    @classmethod
    def normalize_frequency(cls, v):
        if v is None:
            return "weekly"
        s = str(v).strip().lower()
        if s in {"daily", "weekly", "monthly", "rare"}:
            return s
        if "ongoing" in s or "regular" in s or "often" in s or "frequent" in s:
            return "weekly"
        if "day" in s:
            return "daily"
        if "month" in s:
            return "monthly"
        if "rare" in s or "occas" in s or "sporadic" in s or "infrequent" in s:
            return "rare"
        if "/week" in s or "per week" in s:
            return "weekly"
        if "/month" in s or "per month" in s:
            return "monthly"
        return "weekly"


# Keep alias that other modules might import
ActionSchema = Action

# ---------- API payloads ----------


class HealthResponse(BaseModel):
    status: str = "ok"


class ParseRequest(BaseModel):
    resume_text: str
    target_intro: Optional[str] = None


class ParseResponse(BaseModel):
    profile_draft: Profile
    notes: str


class SessionStartRequest(BaseModel):
    resume_text: str
    target_intro: Optional[str] = None


class SessionStartResponse(BaseModel):
    session_id: str
    profile: Profile
    next_question: Optional[Question] = None


class NextQuestionResponse(BaseModel):
    session_id: str
    question: Optional[Question] = None
    remaining_gaps: int = 0


class AnswerRequest(BaseModel):
    question_id: str
    answer_text: str


class AnswerApplyResponse(BaseModel):
    session_id: str
    profile: Profile
    notes: Optional[str] = None
    checked: Optional[CheckedGap] = None
    applied_updates: Optional[List[Dict[str, Any]]] = None
    remaining_gaps: Optional[int] = None


class ProfileResponse(BaseModel):
    session_id: str
    profile: Profile


class SynthesisResponse(BaseModel):
    session_id: str
    summary_text: str
