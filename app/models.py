import time
import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Question(Base):
    __tablename__ = 'questions'
    id: Mapped[int] = mapped_column(primary_key=True)
    section: Mapped[str] = mapped_column(String(10), index=True)
    topic: Mapped[str] = mapped_column(String(80))
    difficulty: Mapped[str] = mapped_column(String(12))
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON)
    correct_index: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(Text)
    source_ref: Mapped[str] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(12), default='draft', index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    origin: Mapped[str] = mapped_column(String(100), default='seed')
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Attempt(Base):
    __tablename__ = 'attempts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(12))
    sections: Mapped[list] = mapped_column(JSON)
    active_section: Mapped[int] = mapped_column(Integer, default=0)
    block: Mapped[int] = mapped_column(Integer, default=0)
    deadline: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), default='active')
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class Item(Base):
    __tablename__ = 'items'
    __table_args__ = (UniqueConstraint('attempt_id', 'position'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('attempts.id'), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id'))
    position: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(10))
    block: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[dict] = mapped_column(JSON)
    answer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)


class Generation(Base):
    __tablename__ = 'generations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    section: Mapped[str] = mapped_column(String(10))
    model: Mapped[str] = mapped_column(String(100))
    count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default='running')
    message: Mapped[str] = mapped_column(Text, default='Generating draft questions…')
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Learner(Base):
    __tablename__ = 'learners'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(24), unique=True)
    password_hash: Mapped[str] = mapped_column(String(250))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class LearnerSession(Base):
    __tablename__ = 'learner_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey('learners.id'), index=True)
    expires_at: Mapped[float] = mapped_column(Float, index=True)


class AttemptProfile(Base):
    __tablename__ = 'attempt_profiles'
    attempt_id: Mapped[str] = mapped_column(ForeignKey('attempts.id'), primary_key=True)
    profile: Mapped[str] = mapped_column(String(64), index=True)


class QuestionResult(Base):
    __tablename__ = 'question_results'
    item_id: Mapped[int] = mapped_column(ForeignKey('items.id'), primary_key=True)
    profile: Mapped[str] = mapped_column(String(64), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id'), index=True)
    correct: Mapped[bool] = mapped_column(Boolean)
    recorded_at: Mapped[float] = mapped_column(Float)
