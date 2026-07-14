from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="shadow")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    agents: Mapped[list[Agent]] = relationship(back_populates="project")
    policies: Mapped[list[Policy]] = relationship(back_populates="project")


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False, default="openai")
    key_hash: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped[Project] = relationship(back_populates="agents")


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    window_size: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="block")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    project: Mapped[Project] = relationship(back_populates="policies")


class GuardSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), nullable=False, index=True)
    external_session_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flagged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blocked_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    requests: Mapped[list[RequestRecord]] = relationship(back_populates="session")
    events: Mapped[list[Event]] = relationship(back_populates="session")


class RequestRecord(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    error_fingerprint: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_tokens: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False, default="allow")
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[GuardSession] = relationship(back_populates="requests")
    tool_calls: Mapped[list[ToolCall]] = relationship(back_populates="request")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), nullable=False, index=True)
    request_id: Mapped[str | None] = mapped_column(ForeignKey("requests.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="info")
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="shadow")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[GuardSession] = relationship(back_populates="events")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    args_hash: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    result_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    request: Mapped[RequestRecord] = relationship(back_populates="tool_calls")

