# backend/app/models.py
from __future__ import annotations
from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base


def now():
    return datetime.utcnow()


class SessionModel(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=now, nullable=False)
    updated_at = Column(DateTime, default=now, onupdate=now, nullable=False)
    use_llm = Column(Boolean, default=False)
    # persisted state
    profile_json = Column(Text, nullable=False)
    resume_text = Column(Text, nullable=True)
    target_intro = Column(Text, nullable=True)

    questions = relationship(
        "QuestionModel", back_populates="session", cascade="all, delete-orphan"
    )
    answers = relationship(
        "AnswerModel", back_populates="session", cascade="all, delete-orphan"
    )
    actions = relationship(
        "ActionModel", back_populates="session", cascade="all, delete-orphan"
    )


class QuestionModel(Base):
    __tablename__ = "questions"
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=now, nullable=False)
    text = Column(Text, nullable=False)
    gap_type = Column(String, nullable=False)
    target = Column(Text, nullable=True)
    rationale = Column(Text, nullable=True)

    session = relationship("SessionModel", back_populates="questions")
    answers = relationship(
        "AnswerModel", back_populates="question", cascade="all, delete-orphan"
    )


class AnswerModel(Base):
    __tablename__ = "answers"
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True, nullable=False)
    question_id = Column(String, ForeignKey("questions.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=now, nullable=False)
    text = Column(Text, nullable=False)  # <-- ensure this exists

    session = relationship("SessionModel", back_populates="answers")
    question = relationship("QuestionModel", back_populates="answers")


class ActionModel(Base):
    __tablename__ = "actions"
    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("sessions.id"), index=True, nullable=False)
    created_at = Column(DateTime, default=now, nullable=False)

    title = Column(Text, nullable=False)
    skill = Column(String, nullable=True)
    project_title = Column(Text, nullable=True)
    period = Column(String, nullable=True)
    tech_stack_json = Column(Text, nullable=True)
    impact = Column(Text, nullable=True)
    mode = Column(String, nullable=True)
    frequency = Column(String, nullable=True)

    session = relationship("SessionModel", back_populates="actions")
