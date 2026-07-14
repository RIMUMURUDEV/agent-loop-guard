from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import AppConfig
from app.core.redaction import redact_text
from app.db.models import (
    Agent,
    Event,
    GuardSession,
    Policy,
    Project,
    RequestRecord,
    ToolCall,
    TraceArtifact,
    TraceEvent,
    TraceRun,
    TraceSpan,
    utcnow,
)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _json_dumps(value: Any) -> str:
    try:
        raw = json.dumps(value or {}, ensure_ascii=False, sort_keys=True)
    except TypeError:
        raw = json.dumps({"value": str(value)}, ensure_ascii=False, sort_keys=True)
    return redact_text(raw) or "{}"


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _dt_to_ns(value: datetime) -> int:
    return int(_aware(value).timestamp() * 1_000_000_000)


def _ns_to_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1_000_000_000, UTC).isoformat()


def _now_ns() -> int:
    return _dt_to_ns(utcnow())


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
        created_at = utcnow()
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
            created_at=created_at,
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
        self._record_proxy_trace(
            session=session,
            record=record,
            protocol=protocol,
            endpoint=endpoint,
            model=model,
            latency_ms=latency_ms,
            tokens=tokens,
            decision=decision,
            reason_code=reason_code,
            request_preview=request_preview,
            response_preview=response_preview,
            tool_calls=tool_calls,
            error_fingerprint=error_fingerprint,
        )
        self.db.commit()
        return record

    def ensure_trace_for_session(self, session: GuardSession) -> tuple[TraceRun, TraceSpan]:
        run = self.db.scalar(
            select(TraceRun).where(TraceRun.source_session_id == session.id).limit(1)
        )
        root = None
        if run is not None:
            root = self.db.scalar(
                select(TraceSpan)
                .where(
                    TraceSpan.trace_id == run.id,
                    TraceSpan.parent_span_id.is_(None),
                    TraceSpan.name == "agent.run",
                )
                .limit(1)
            )

        if run is None:
            agent = self.db.get(Agent, session.agent_id)
            run = TraceRun(
                id=new_id("trc"),
                source_session_id=session.id,
                project_id=session.project_id,
                task_id=session.external_session_id,
                task_fingerprint=key_hash(session.external_session_id or session.id),
                agent_name=agent.name if agent else session.agent_id,
                status="running" if session.status == "active" else session.status,
                input_tokens=session.input_tokens,
                output_tokens=session.output_tokens,
                total_tokens=session.total_tokens,
                duration_ms=max(0, int((utcnow() - _aware(session.started_at)).total_seconds() * 1000)),
                span_count=1,
                event_count=0,
                attributes_json=_json_dumps(
                    {
                        "source": "agent_loop_guard",
                        "session.id": session.id,
                        "session.external_id": session.external_session_id,
                        "project.id": session.project_id,
                        "agent.id": session.agent_id,
                    }
                ),
            )
            self.db.add(run)
            root = TraceSpan(
                id=new_id("spn"),
                trace_id=run.id,
                parent_span_id=None,
                name="agent.run",
                status="ok",
                start_ns=_dt_to_ns(session.started_at),
                end_ns=None,
                duration_ms=run.duration_ms,
                attributes_json=_json_dumps(
                    {
                        "agent.name": run.agent_name,
                        "project.id": session.project_id,
                        "session.id": session.id,
                        "task.id": session.external_session_id,
                    }
                ),
            )
            self.db.add(root)
        elif root is None:
            root = TraceSpan(
                id=new_id("spn"),
                trace_id=run.id,
                parent_span_id=None,
                name="agent.run",
                status="ok",
                start_ns=_dt_to_ns(session.started_at),
                end_ns=None,
                duration_ms=run.duration_ms,
                attributes_json=_json_dumps({"session.id": session.id}),
            )
            self.db.add(root)
            run.span_count = (run.span_count or 0) + 1

        run.status = "running" if session.status == "active" else session.status
        run.input_tokens = session.input_tokens
        run.output_tokens = session.output_tokens
        run.total_tokens = session.total_tokens
        run.updated_at = utcnow()
        run.duration_ms = max(0, int((run.updated_at - _aware(session.started_at)).total_seconds() * 1000))
        root.duration_ms = run.duration_ms
        return run, root

    def _record_proxy_trace(
        self,
        *,
        session: GuardSession,
        record: RequestRecord,
        protocol: str,
        endpoint: str,
        model: str | None,
        latency_ms: int,
        tokens: dict[str, int | bool],
        decision: str,
        reason_code: str | None,
        request_preview: str | None,
        response_preview: str | None,
        tool_calls: list[tuple[str, str]],
        error_fingerprint: str | None,
    ) -> None:
        run, root = self.ensure_trace_for_session(session)
        end_ns = _dt_to_ns(record.created_at)
        start_ns = max(0, end_ns - (latency_ms * 1_000_000))
        span_status = "error" if record.status >= 400 or decision == "block" else "ok"
        if decision == "block":
            span_status = "blocked"
        span = TraceSpan(
            id=new_id("spn"),
            trace_id=run.id,
            parent_span_id=root.id,
            name="gen_ai.request",
            status=span_status,
            start_ns=start_ns,
            end_ns=end_ns,
            duration_ms=latency_ms,
            attributes_json=_json_dumps(
                {
                    "request.id": record.id,
                    "gen_ai.system": protocol,
                    "gen_ai.request.model": model,
                    "http.route": endpoint,
                    "http.status_code": record.status,
                    "input_tokens": int(tokens.get("input_tokens", 0)),
                    "output_tokens": int(tokens.get("output_tokens", 0)),
                    "total_tokens": int(tokens.get("total_tokens", 0)),
                    "tokens.estimated": bool(tokens.get("estimated", True)),
                    "policy.decision": decision,
                    "policy.reason": reason_code,
                    "request.preview": request_preview,
                    "response.preview": response_preview,
                    "error.fingerprint": error_fingerprint,
                    "tool.count": len(tool_calls),
                }
            ),
        )
        self.db.add(span)
        run.span_count = (run.span_count or 0) + 1
        run.model = run.model or model
        run.failure_tag = reason_code or run.failure_tag
        if span_status in {"error", "blocked"}:
            run.status = span_status
        run.updated_at = record.created_at

        if reason_code:
            self.db.add(
                TraceEvent(
                    id=new_id("tev"),
                    trace_id=run.id,
                    span_id=span.id,
                    name="policy.decision",
                    severity="error" if decision == "block" else "warning",
                    timestamp_ns=end_ns,
                    attributes_json=_json_dumps(
                        {
                            "decision": decision,
                            "reason_code": reason_code,
                            "request.id": record.id,
                        }
                    ),
                )
            )
            run.event_count = (run.event_count or 0) + 1

        for tool_name, args_hash in tool_calls:
            self.db.add(
                TraceEvent(
                    id=new_id("tev"),
                    trace_id=run.id,
                    span_id=span.id,
                    name="tool.reference",
                    severity="info",
                    timestamp_ns=end_ns,
                    attributes_json=_json_dumps(
                        {"tool.name": tool_name, "tool.arguments_hash": args_hash}
                    ),
                )
            )
            run.event_count = (run.event_count or 0) + 1

    def create_trace_run(self, data: dict[str, Any]) -> TraceRun:
        trace_id = str(data.get("trace_id") or data.get("id") or new_id("trc"))
        run = self.db.get(TraceRun, trace_id)
        if run is None:
            run = TraceRun(id=trace_id)
            self.db.add(run)
        run.project_id = str(data.get("project_id") or run.project_id or "default")
        run.task_id = data.get("task_id") or run.task_id
        task_fingerprint = data.get("task_fingerprint")
        if task_fingerprint is None and run.task_id:
            task_fingerprint = key_hash(str(run.task_id))
        run.task_fingerprint = task_fingerprint or run.task_fingerprint
        run.agent_name = data.get("agent_name") or run.agent_name
        run.model = data.get("model") or run.model
        run.status = str(data.get("status") or run.status or "running")
        run.failure_tag = data.get("failure_tag") or run.failure_tag
        run.input_tokens = int(data.get("input_tokens") or run.input_tokens or 0)
        run.output_tokens = int(data.get("output_tokens") or run.output_tokens or 0)
        run.total_tokens = int(data.get("total_tokens") or run.total_tokens or 0)
        run.total_cost_micros = int(data.get("total_cost_micros") or run.total_cost_micros or 0)
        run.pinned = bool(data.get("pinned", run.pinned))
        run.attributes_json = _json_dumps(data.get("attributes") or _json_loads(run.attributes_json))
        run.updated_at = utcnow()

        if not self.db.scalar(select(TraceSpan.id).where(TraceSpan.trace_id == run.id).limit(1)):
            self.db.add(
                TraceSpan(
                    id=new_id("spn"),
                    trace_id=run.id,
                    parent_span_id=None,
                    name="agent.run",
                    status=run.status if run.status != "running" else "ok",
                    start_ns=int(data.get("start_ns") or _now_ns()),
                    end_ns=data.get("end_ns"),
                    duration_ms=int(data.get("duration_ms") or 0),
                    attributes_json=_json_dumps(
                        {
                            "agent.name": run.agent_name,
                            "project.id": run.project_id,
                            "task.id": run.task_id,
                        }
                    ),
                )
            )
            run.span_count = 1

        self.db.commit()
        self.refresh_trace_summary(run.id)
        return self.db.get(TraceRun, run.id) or run

    def add_trace_span(self, trace_id: str, data: dict[str, Any]) -> TraceSpan | None:
        run = self.db.get(TraceRun, trace_id)
        if run is None:
            return None
        span_id = str(data.get("span_id") or data.get("id") or new_id("spn"))
        span = self.db.get(TraceSpan, span_id)
        if span is None:
            span = TraceSpan(id=span_id, trace_id=trace_id, start_ns=int(data.get("start_ns") or _now_ns()), name="span")
            self.db.add(span)
        span.trace_id = trace_id
        span.parent_span_id = data.get("parent_span_id")
        span.name = str(data.get("name") or span.name)
        span.status = str(data.get("status") or span.status or "ok")
        span.start_ns = int(data.get("start_ns") or span.start_ns or _now_ns())
        end_ns = data.get("end_ns")
        span.end_ns = int(end_ns) if end_ns is not None else None
        if span.end_ns is not None:
            span.duration_ms = max(0, int((span.end_ns - span.start_ns) / 1_000_000))
        else:
            span.duration_ms = int(data.get("duration_ms") or span.duration_ms or 0)
        span.attributes_json = _json_dumps(data.get("attributes") or _json_loads(span.attributes_json))
        run.updated_at = utcnow()
        self.db.commit()
        self.refresh_trace_summary(trace_id)
        return self.db.get(TraceSpan, span.id) or span

    def add_trace_events(self, trace_id: str, rows: list[dict[str, Any]]) -> list[TraceEvent] | None:
        run = self.db.get(TraceRun, trace_id)
        if run is None:
            return None
        events: list[TraceEvent] = []
        for row in rows:
            event = TraceEvent(
                id=str(row.get("event_id") or row.get("id") or new_id("tev")),
                trace_id=trace_id,
                span_id=row.get("span_id"),
                name=str(row.get("name") or row.get("type") or "event"),
                severity=str(row.get("severity") or "info"),
                timestamp_ns=int(row.get("timestamp_ns") or _now_ns()),
                attributes_json=_json_dumps(row.get("attributes") or row.get("details") or {}),
            )
            self.db.add(event)
            events.append(event)
        run.updated_at = utcnow()
        self.db.commit()
        self.refresh_trace_summary(trace_id)
        return events

    def add_trace_artifact(self, trace_id: str, data: dict[str, Any]) -> TraceArtifact | None:
        run = self.db.get(TraceRun, trace_id)
        if run is None:
            return None
        artifact = TraceArtifact(
            id=str(data.get("artifact_id") or data.get("id") or new_id("art")),
            trace_id=trace_id,
            path=str(data.get("path") or ""),
            mime_type=data.get("mime_type"),
            size=int(data.get("size") or 0),
            sha256=data.get("sha256"),
            attributes_json=_json_dumps(data.get("attributes") or {}),
        )
        self.db.add(artifact)
        run.updated_at = utcnow()
        self.db.commit()
        return artifact

    def refresh_trace_summary(self, trace_id: str) -> None:
        run = self.db.get(TraceRun, trace_id)
        if run is None:
            return
        run.span_count = int(
            self.db.scalar(select(func.count(TraceSpan.id)).where(TraceSpan.trace_id == trace_id))
            or 0
        )
        run.event_count = int(
            self.db.scalar(select(func.count(TraceEvent.id)).where(TraceEvent.trace_id == trace_id))
            or 0
        )
        first_start = self.db.scalar(
            select(func.min(TraceSpan.start_ns)).where(TraceSpan.trace_id == trace_id)
        )
        last_end = self.db.scalar(
            select(func.max(func.coalesce(TraceSpan.end_ns, TraceSpan.start_ns))).where(
                TraceSpan.trace_id == trace_id
            )
        )
        if first_start is not None and last_end is not None:
            run.duration_ms = max(0, int((int(last_end) - int(first_start)) / 1_000_000))
        run.updated_at = utcnow()
        self.db.commit()

    def list_trace_runs(
        self, limit: int = 50, project_id: str | None = None, query: str | None = None
    ) -> list[TraceRun]:
        statement = select(TraceRun)
        if project_id:
            statement = statement.where(TraceRun.project_id == project_id)
        if query:
            pattern = f"%{query}%"
            statement = statement.where(
                TraceRun.id.like(pattern)
                | TraceRun.task_id.like(pattern)
                | TraceRun.agent_name.like(pattern)
                | TraceRun.model.like(pattern)
                | TraceRun.failure_tag.like(pattern)
            )
        statement = statement.order_by(desc(TraceRun.updated_at)).limit(limit)
        return list(self.db.scalars(statement))

    def get_trace_run(self, trace_id: str) -> TraceRun | None:
        return self.db.get(TraceRun, trace_id)

    def trace_spans(self, trace_id: str) -> list[TraceSpan]:
        return list(
            self.db.scalars(
                select(TraceSpan).where(TraceSpan.trace_id == trace_id).order_by(TraceSpan.start_ns)
            )
        )

    def trace_events(self, trace_id: str) -> list[TraceEvent]:
        return list(
            self.db.scalars(
                select(TraceEvent)
                .where(TraceEvent.trace_id == trace_id)
                .order_by(TraceEvent.timestamp_ns)
            )
        )

    def trace_artifacts(self, trace_id: str) -> list[TraceArtifact]:
        return list(
            self.db.scalars(
                select(TraceArtifact)
                .where(TraceArtifact.trace_id == trace_id)
                .order_by(TraceArtifact.created_at)
            )
        )

    def trace_export(self, trace_id: str) -> dict[str, Any] | None:
        run = self.get_trace_run(trace_id)
        if run is None:
            return None
        return {
            "schema_version": "trace.v1",
            "run": trace_run_dict(run),
            "spans": [trace_span_dict(item) for item in self.trace_spans(trace_id)],
            "events": [trace_event_dict(item) for item in self.trace_events(trace_id)],
            "artifacts": [trace_artifact_dict(item) for item in self.trace_artifacts(trace_id)],
        }

    def compare_traces(self, left_id: str, right_id: str) -> dict[str, Any] | None:
        left = self.get_trace_run(left_id)
        right = self.get_trace_run(right_id)
        if left is None or right is None:
            return None
        fields = ("duration_ms", "input_tokens", "output_tokens", "total_tokens", "total_cost_micros", "span_count", "event_count")
        deltas = {field: getattr(right, field) - getattr(left, field) for field in fields}
        left_spans = self.trace_spans(left_id)
        right_spans = self.trace_spans(right_id)
        left_by_name: dict[str, int] = {}
        right_by_name: dict[str, int] = {}
        for span in left_spans:
            left_by_name[span.name] = left_by_name.get(span.name, 0) + 1
        for span in right_spans:
            right_by_name[span.name] = right_by_name.get(span.name, 0) + 1
        span_name_deltas = {
            name: right_by_name.get(name, 0) - left_by_name.get(name, 0)
            for name in sorted(set(left_by_name) | set(right_by_name))
        }
        return {
            "schema_version": "trace.compare.v1",
            "left": trace_run_dict(left),
            "right": trace_run_dict(right),
            "delta": deltas,
            "span_name_delta": span_name_deltas,
        }

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
        traces = int(self.db.scalar(select(func.count(TraceRun.id))) or 0)
        spans = int(self.db.scalar(select(func.count(TraceSpan.id))) or 0)
        trace_events = int(self.db.scalar(select(func.count(TraceEvent.id))) or 0)
        flags = int(self.db.scalar(select(func.coalesce(func.sum(GuardSession.flagged_count), 0))) or 0)
        blocks = int(self.db.scalar(select(func.coalesce(func.sum(GuardSession.blocked_count), 0))) or 0)
        tokens = int(self.db.scalar(select(func.coalesce(func.sum(GuardSession.total_tokens), 0))) or 0)
        return {
            "sessions": sessions,
            "requests": requests,
            "traces": traces,
            "spans": spans,
            "trace_events": trace_events,
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


def trace_run_dict(run: TraceRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "source_session_id": run.source_session_id,
        "project_id": run.project_id,
        "task_id": run.task_id,
        "task_fingerprint": run.task_fingerprint,
        "agent_name": run.agent_name,
        "model": run.model,
        "status": run.status,
        "failure_tag": run.failure_tag,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "total_tokens": run.total_tokens,
        "total_cost_micros": run.total_cost_micros,
        "duration_ms": run.duration_ms,
        "span_count": run.span_count,
        "event_count": run.event_count,
        "pinned": run.pinned,
        "attributes": _json_loads(run.attributes_json),
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def trace_span_dict(span: TraceSpan) -> dict[str, Any]:
    return {
        "id": span.id,
        "trace_id": span.trace_id,
        "parent_span_id": span.parent_span_id,
        "name": span.name,
        "status": span.status,
        "start_ns": span.start_ns,
        "end_ns": span.end_ns,
        "start_at": _ns_to_iso(span.start_ns),
        "end_at": _ns_to_iso(span.end_ns),
        "duration_ms": span.duration_ms,
        "attributes": _json_loads(span.attributes_json),
    }


def trace_event_dict(event: TraceEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "trace_id": event.trace_id,
        "span_id": event.span_id,
        "name": event.name,
        "severity": event.severity,
        "timestamp_ns": event.timestamp_ns,
        "timestamp": _ns_to_iso(event.timestamp_ns),
        "attributes": _json_loads(event.attributes_json),
    }


def trace_artifact_dict(artifact: TraceArtifact) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "trace_id": artifact.trace_id,
        "path": artifact.path,
        "mime_type": artifact.mime_type,
        "size": artifact.size,
        "sha256": artifact.sha256,
        "attributes": _json_loads(artifact.attributes_json),
        "created_at": artifact.created_at.isoformat(),
    }
