# backend/app/llm_schema.py
from pydantic import BaseModel, Field
from typing import List, Any


class UpdateItem(BaseModel):
    path: str = Field(
        ..., description="e.g., skills[Python].depth or projects[0].impact.delta"
    )
    value: Any
    confidence: float = 0.7
    evidence: str | None = None


class UpdateBundle(BaseModel):
    updates: List[UpdateItem]
    notes: str | None = None
