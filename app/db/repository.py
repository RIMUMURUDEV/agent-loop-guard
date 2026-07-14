from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import AppConfig
from app.db.models import (
    Agent,
    Event,
    GuardSession,
    Policy,
    Project,
    RequestRecord,
    ToolCall,
    utcnow,
)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def default_policies(project_id: str) -> list[Policy]:
    return [
        Policy(
            id="rule_exact_repeat",
            project_id=project_id,
            rule_type="exact_repeat",
            threshold=3,
            window_size=8,
            action="block",
            enabled=True,
        ),
        Policy(
            id="rule_tool_repeat",
            project_id=project_id,
            rule_type="tool_repeat",
            threshold=3,
            window_size=8,
            action="block",
            enabled=True,
        ),
        Policy(
            id="rule_error_retry",
            project_id=project_id,
            rule_type="error_retry",
            threshold=5,
            window_size=5,
            action="block",
            enabled=True,
        ),
        Policy(
            id="rule_sequence",
            project_id=project_id,
            rule_type="sequence_repeat",
            threshold=3,
            window_size=15,
            action="block",
            enabled=True,
        ),
        Policy(
            id="rule_max_requests",
            project_id=project_id,
            rule_type="max_requests",
            threshold=50,
            window_size=0,
            action="block",
            enabled=True,
        ),
        Policy(
            id="rule_max_tokens",
            project_id=project_id,
            rule_type="max_tokens",
            threshold=100_000,
            window_size=0,
            action="block",
            enabled=True,
        ),
    ]


def ensure_seed_data(db: Session, config: AppConfig) -> None:
    project = db.get(Project, config.default_project_id)
    if project is None:
        project = Project(
            id=config.default_project_id,
            name="Default project",
            mode=config.default_mode,
            provider=config.default_provider,
        )
        db.add(project)

    default_agent = db.get(Agent, "agt_default")
    if default_agent is None:
        default_agent = Agent(
            id="agt_default",
            project_id=config.default_project_id,
            name="Default local agent",
            protocol="openai",
            key_hash=key_hash(config.gateway_key),
            enabled=True,
        )
        db.add(default_agent)

    existing_policy_count = db.scalar(
        select(func.count(Policy.id)).where(Policy.project_id == config.default_project_id)
    )
    if not existing_policy_count:
        db.add_all(default_policies(config.default_project_id))

    db.commit()


class Repository:
    def __init__(self, db: Session):
        self.db = db

    def agent_for_key(self, raw_key: str) -> Agent | None:
        digest = key_hash(raw_key)
        return self.db.scalar(
            select(Agent).where(Agent.key_hash == digest, Agent.enabled.is_(True)).limit(1)
        )

    def project(self, project_id: str) -> Project | None:
        return self.db.get(Project, project_id)

    def policies(self, project_id: str) -> list[Policy]:
        return list(
            self.db.scalars(select(Policy).where(Policy.project_id == project_id).order_by(Policy.id))
        )

    def upsert_policies(self, project_id: str, rows: list[dict[str, Any]]) -> list[Policy]:
        existing = {p.id: p for p in self.policies(project_id)}
        for row in rows:
            policy_id = str(row.get("id") or f"rule_{row['rule_type']}")
            policy = existing.get(policy_id)
            if policy is None:
                policy = Policy(id=policy_id, project_id=project_id, rule_type=str(row["rule_type"]))
                self.db.add(policy)
            policy.threshold = int(row.get("threshold", policy.threshold or 1))
            policy.window_size = int(row.get("window_size", policy.window_size or 0))
            policy.action = str(row.get("action", policy.action or "block"))
            policy.enabled = bool(row.get("enabled", policy.enabled))
        self.db.commit()
        return self.policies(project_id)

    def create_agent(
        self, project_id: str, name: str, protocol: str = "openai", raw_key: str | None = None
    ) -> tuple[Agent, str]:
        raw_key = raw_key or f"alg_{uuid.uuid4().hex}"
        agent = Agent(
            id=new_id("agt"),
            project_id=project_id,
            name=name,
            protocol=protocol,
            key_hash=key_hash(raw_key),
            enabled=True,
        )
        self.db.add(agent)
        self.db.commit()
        return agent, raw_key

    def list_agents(self) -> list[Agent]:
        return list(self.db.scalars(select(Agent).order_by(Agent.created_at.desc())))

    def pause_agent(self, agent_id: str) -> Agent | None:
        agent = self.db.get(Agent, agent_id)
        if agent is None:
            return None
        agent.paused = True
        self.db.commit()
        return agent

    def resume_agent(self, agent_id: str) -> Agent | None:
        agent = self.db.get(Agent, agent_id)
        if agent is None:
            return None
        agent.paused = False
        self.db.commit()
        return agent

    def get_or_create_session(
        self,
        project_id: str,
        agent_id: str,
        external_session_id: str | None,
        inactive_timeout_seconds: int,
    ) -> GuardSession:
        query = select(GuardSession).where(
            GuardSession.project_id == project_id,
            GuardSession.agent_id == agent_id,
            GuardSession.status.in_(["active", "paused"]),
        )
        if external_session_id:
            query = query.where(GuardSession.external_session_id == external_session_id)
        else:
            query = query.where(GuardSession.external_session_id.is_(None))
        query = query.order_by(desc(GuardSession.updated_at)).limit(1)
        session = self.db.scalar(query)
        now = utcnow()
        if session is not None:
            if now - _aware(session.updated_at) <= timedelta(seconds=inactive_timeout_seconds):
                return session
            session.status = "ended"
            session.ended_at = now

        session = GuardSession(
            id=new_id("ses"),
            project_id=project_id,
            agent_id=agent_id,
            external_session_id=external_session_id,
            status="active",
        )
        self.db.add(session)
        self.db.commit()
        return session

    def get_session(self, session_id: str) -> GuardSession | None:
        return self.db.get(GuardSession, session_id)

    def list_sessions(self, limit: int = 50) -> list[GuardSession]:
        return list(
            self.db.scalars(select(GuardSession).order_by(desc(GuardSession.updated_at)).limit(limit))
        )

    def update_session(
        self, session_id: str, *, name: str | None = None, note: str | None = None
    ) -> GuardSession | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        if name is not None:
            session.name = name.strip() or None
        if note is not None:
            session.note = note.strip() or None
        session.updated_at = utcnow()
        self.db.commit()
        return session

    def pause_session(self, session_id: str) -> GuardSession | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        session.status = "paused"
        session.updated_at = utcnow()
        self.event(session.id, None, "manual_pause", "info", "SESSION_PAUSED", "manual", {})
        self.db.commit()
        return session

    def resume_session(self, session_id: str) -> GuardSession | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        session.status = "active"
        session.updated_at = utcnow()
        self.event(session.id, None, "manual_resume", "info", "SESSION_RESUMED", "manual", {})
        self.db.commit()
        return session

    def recent_request_fingerprints(self, session_id: str, limit: int) -> list[str]:
        rows = list(
            self.db.scalars(
                select(RequestRecord.fingerprint)
                .where(RequestRecord.session_id == session_id)
                .order_by(desc(RequestRecord.created_at))
                .limit(limit)
            )
        )
        return list(reversed(rows))

    def recent_tool_fingerprints(self, session_id: str, limit: int) -> list[str]:
        rows = list(
            self.db.execute(
                select(ToolCall.tool_name, ToolCall.args_hash)
                .join(RequestRecord, RequestRecord.id == ToolCall.request_id)
                .where(RequestRecord.session_id == session_id)
                .order_by(desc(RequestRecord.created_at))
                .limit(limit)
            )
        )
        return [f"{name}:{args_hash}" for name, args_hash in reversed(rows)]

    def consecutive_error_count(self, session_id: str) -> tuple[str | None, int]:
        rows = list(
            self.db.scalars(
                select(RequestRecord.error_fingerprint)
                .where(RequestRecord.session_id == session_id)
                .order_by(desc(RequestRecord.created_at))
                .limit(20)
            )
        )
        first = rows[0] if rows else None
        if not first:
            return None, 0
        count = 0
        for row in rows:
            if row == first:
                count += 1
            else:
                break
        return first, count

    def record_request(
        self,
        session: GuardSession,
        protocol: str,
        endpoint: str,
        model: str | None,
        fingerprint: str,
        status: int,
        latency_ms: int,
        tokens: dict[str, int | bool],
        decision: str,
        reason_code: str | None,
        request_preview: str | None,
        response_preview: str | None,
        tool_calls: list[tuple[str, str]],
        error_fingerprint: str | None = None,
    ) -> RequestRecord:
        record = RequestRecord(
            id=new_id("req"),
            session_id=session.id,
            protocol=protocol,
            endpoint=endpoint,
            model=model,
            fingerprint=fingerprint,
            error_fingerprint=error_fingerprint,
            status=status,
            latency_ms=latency_ms,
            input_tokens=int(tokens.get("input_tokens", 0)),
            output_tokens=int(tokens.get("output_tokens", 0)),
            total_tokens=int(tokens.get("total_tokens", 0)),
            estimated_tokens=bool(tokens.get("estimated", True)),
            decision=decision,
            reason_code=reason_code,
            request_preview=request_preview,
            response_preview=response_preview,
        )
        self.db.add(record)
        for name, args_hash in tool_calls:
            self.db.add(
                ToolCall(
                    id=new_id("tool"),
                    request_id=record.id,
                    tool_name=name[:160],
                    args_hash=args_hash,
                )
            )

        session.request_count += 1
        session.input_tokens += record.input_tokens
        session.output_tokens += record.output_tokens
        session.total_tokens += record.total_tokens
        session.updated_at = utcnow()
        if decision == "block":
            session.blocked_count += 1
        elif decision == "shadow_flag":
            session.flagged_count += 1
        self.db.commit()
        return record

    def event(
        self,
        session_id: str,
        request_id: str | None,
        event_type: str,
        severity: str,
        reason_code: str | None,
        mode: str,
        payload: dict[str, Any],
        rule_id: str | None = None,
    ) -> Event:
        event = Event(
            id=new_id("evt"),
            session_id=session_id,
            request_id=request_id,
            type=event_type,
            rule_id=rule_id,
            severity=severity,
            reason_code=reason_code,
            mode=mode,
            payload_json=json.dumps(payload, sort_keys=True),
        )
        self.db.add(event)
        self.db.commit()
        return event

    def events_for_session(self, session_id: str) -> list[Event]:
        return list(
            self.db.scalars(select(Event).where(Event.session_id == session_id).order_by(Event.created_at))
        )

    def requests_for_session(self, session_id: str) -> list[RequestRecord]:
        return list(
            self.db.scalars(
                select(RequestRecord)
                .where(RequestRecord.session_id == session_id)
                .order_by(RequestRecord.created_at)
            )
        )

    def aggregate_stats(self) -> dict[str, int]:
        sessions = int(self.db.scalar(select(func.count(GuardSession.id))) or 0)
        requests = int(self.db.scalar(select(func.count(RequestRecord.id))) or 0)
        flags = int(self.db.scalar(select(func.coalesce(func.sum(GuardSession.flagged_count), 0))) or 0)
        blocks = int(self.db.scalar(select(func.coalesce(func.sum(GuardSession.blocked_count), 0))) or 0)
        tokens = int(self.db.scalar(select(func.coalesce(func.sum(GuardSession.total_tokens), 0))) or 0)
        return {
            "sessions": sessions,
            "requests": requests,
            "flags": flags,
            "blocks": blocks,
            "tokens": tokens,
        }


def event_dict(event: Event) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "event_id": event.id,
        "session_id": event.session_id,
        "request_id": event.request_id,
        "type": event.type,
        "severity": event.severity,
        "rule_id": event.rule_id,
        "reason_code": event.reason_code,
        "mode": event.mode,
        "created_at": event.created_at.isoformat(),
        "details": json.loads(event.payload_json or "{}"),
    }


def request_dict(record: RequestRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "protocol": record.protocol,
        "endpoint": record.endpoint,
        "model": record.model,
        "fingerprint": record.fingerprint,
        "error_fingerprint": record.error_fingerprint,
        "status": record.status,
        "latency_ms": record.latency_ms,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "total_tokens": record.total_tokens,
        "estimated_tokens": record.estimated_tokens,
        "decision": record.decision,
        "reason_code": record.reason_code,
        "created_at": record.created_at.isoformat(),
    }


def session_dict(session: GuardSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "project_id": session.project_id,
        "agent_id": session.agent_id,
        "external_session_id": session.external_session_id,
        "status": session.status,
        "name": session.name,
        "note": session.note,
        "started_at": session.started_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "request_count": session.request_count,
        "input_tokens": session.input_tokens,
        "output_tokens": session.output_tokens,
        "total_tokens": session.total_tokens,
        "flagged_count": session.flagged_count,
        "blocked_count": session.blocked_count,
    }


def policy_dict(policy: Policy) -> dict[str, Any]:
    return {
        "id": policy.id,
        "project_id": policy.project_id,
        "rule_type": policy.rule_type,
        "threshold": policy.threshold,
        "window_size": policy.window_size,
        "action": policy.action,
        "enabled": policy.enabled,
    }


def agent_dict(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "project_id": agent.project_id,
        "name": agent.name,
        "protocol": agent.protocol,
        "enabled": agent.enabled,
        "paused": agent.paused,
        "created_at": agent.created_at.isoformat(),
    }
