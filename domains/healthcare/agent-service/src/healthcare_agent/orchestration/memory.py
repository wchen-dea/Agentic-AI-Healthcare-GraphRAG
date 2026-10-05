"""Conversation memory and session management.

Provides pluggable session stores for multi-turn conversations:
- InMemorySessionStore (default): fast, no dependencies, lost on restart
- RedisSessionStore: persistent cross-session memory via Redis

Set SESSION_STORE_BACKEND=redis and REDIS_URL to enable Redis persistence.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ConversationTurn:
    question: str
    answer: str
    patient_id: str | None = None
    request_type: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserPreferences:
    preferred_detail_level: str = "standard"  # brief, standard, detailed
    preferred_focus: str = ""  # medication_safety, lab_interpretation, etc.
    acknowledged_patients: set[str] = field(default_factory=set)


class ConversationSession:
    """Manages a single user's conversation context."""

    def __init__(self, session_id: str, max_turns: int = 20, ttl_seconds: int = 3600):
        self.session_id = session_id
        self.turns: deque[ConversationTurn] = deque(maxlen=max_turns)
        self.preferences = UserPreferences()
        self.created_at = time.time()
        self.last_active = time.time()
        self.ttl_seconds = ttl_seconds

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.last_active) > self.ttl_seconds

    def add_turn(self, question: str, answer: str, **kwargs: Any) -> None:
        self.turns.append(ConversationTurn(question=question, answer=answer, **kwargs))
        self.last_active = time.time()

    def get_context_summary(self, max_turns: int = 3) -> str:
        """Build a context string from recent conversation history."""
        if not self.turns:
            return ""

        recent = list(self.turns)[-max_turns:]
        lines = ["Previous conversation:"]
        for turn in recent:
            lines.append(f"Q: {turn.question[:100]}")
            lines.append(f"A: {turn.answer[:150]}")
        return "\n".join(lines)

    def get_mentioned_patients(self) -> set[str]:
        """Return all patient IDs mentioned in this session."""
        patients: set[str] = set()
        for turn in self.turns:
            if turn.patient_id:
                patients.add(turn.patient_id)
        return patients

    def update_preferences(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if hasattr(self.preferences, key):
                setattr(self.preferences, key, value)
        self.last_active = time.time()


class SessionStoreProtocol(Protocol):
    def get_or_create(self, session_id: str) -> ConversationSession: ...
    def get(self, session_id: str) -> ConversationSession | None: ...
    def delete(self, session_id: str) -> None: ...
    @property
    def active_count(self) -> int: ...


class SessionStore:
    """In-memory session store with TTL-based expiration."""

    def __init__(self, max_sessions: int = 1000):
        self._sessions: dict[str, ConversationSession] = {}
        self._max_sessions = max_sessions

    def get_or_create(self, session_id: str) -> ConversationSession:
        self._evict_expired()
        if session_id not in self._sessions:
            if len(self._sessions) >= self._max_sessions:
                self._evict_oldest()
            self._sessions[session_id] = ConversationSession(session_id)
        session = self._sessions[session_id]
        session.last_active = time.time()
        return session

    def get(self, session_id: str) -> ConversationSession | None:
        session = self._sessions.get(session_id)
        if session and not session.is_expired:
            return session
        if session:
            del self._sessions[session_id]
        return None

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    def _evict_expired(self) -> None:
        expired = [sid for sid, s in self._sessions.items() if s.is_expired]
        for sid in expired:
            del self._sessions[sid]

    def _evict_oldest(self) -> None:
        if not self._sessions:
            return
        oldest = min(self._sessions.items(), key=lambda x: x[1].last_active)
        del self._sessions[oldest[0]]


def generate_session_id(user_id: str = "", ip: str = "") -> str:
    """Generate a deterministic session ID from user context."""
    raw = f"{user_id}:{ip}:{int(time.time() // 3600)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _serialize_session(session: ConversationSession) -> str:
    turns = [
        {
            "question": t.question,
            "answer": t.answer,
            "patient_id": t.patient_id,
            "request_type": t.request_type,
            "timestamp": t.timestamp,
            "metadata": t.metadata,
        }
        for t in session.turns
    ]
    return json.dumps({
        "session_id": session.session_id,
        "turns": turns,
        "preferences": {
            "preferred_detail_level": session.preferences.preferred_detail_level,
            "preferred_focus": session.preferences.preferred_focus,
            "acknowledged_patients": sorted(session.preferences.acknowledged_patients),
        },
        "created_at": session.created_at,
        "last_active": session.last_active,
    })


def _deserialize_session(data: str) -> ConversationSession:
    obj = json.loads(data)
    session = ConversationSession(obj["session_id"])
    session.created_at = obj.get("created_at", time.time())
    session.last_active = obj.get("last_active", time.time())
    prefs = obj.get("preferences", {})
    session.preferences.preferred_detail_level = prefs.get("preferred_detail_level", "standard")
    session.preferences.preferred_focus = prefs.get("preferred_focus", "")
    session.preferences.acknowledged_patients = set(prefs.get("acknowledged_patients", []))
    for t in obj.get("turns", []):
        session.turns.append(ConversationTurn(
            question=t["question"],
            answer=t["answer"],
            patient_id=t.get("patient_id"),
            request_type=t.get("request_type", ""),
            timestamp=t.get("timestamp", time.time()),
            metadata=t.get("metadata", {}),
        ))
    return session


class RedisSessionStore:
    """Redis-backed persistent session store with TTL expiration."""

    _KEY_PREFIX = "session:"

    def __init__(self, redis_url: str = "redis://localhost:6379/0", ttl_seconds: int = 3600):
        try:
            import redis
        except ImportError:
            raise ImportError("redis package required: pip install redis")
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"{self._KEY_PREFIX}{session_id}"

    def get_or_create(self, session_id: str) -> ConversationSession:
        session = self.get(session_id)
        if session:
            return session
        session = ConversationSession(session_id, ttl_seconds=self._ttl)
        self._save(session)
        return session

    def get(self, session_id: str) -> ConversationSession | None:
        data = self._client.get(self._key(session_id))
        if data is None:
            return None
        session = _deserialize_session(data)
        session.last_active = time.time()
        return session

    def save(self, session: ConversationSession) -> None:
        self._save(session)

    def _save(self, session: ConversationSession) -> None:
        self._client.setex(self._key(session.session_id), self._ttl, _serialize_session(session))

    def delete(self, session_id: str) -> None:
        self._client.delete(self._key(session_id))

    @property
    def active_count(self) -> int:
        keys = self._client.keys(f"{self._KEY_PREFIX}*")
        return len(keys)


# Singleton store — backend selected by SESSION_STORE_BACKEND env var
_store: SessionStoreProtocol | None = None


def get_session_store() -> SessionStoreProtocol:
    global _store
    if _store is not None:
        return _store

    backend = os.getenv("SESSION_STORE_BACKEND", "memory").lower()
    if backend == "redis":
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        ttl = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
        _store = RedisSessionStore(redis_url=redis_url, ttl_seconds=ttl)
    else:
        _store = SessionStore()
    return _store


def get_patient_memory_store() -> "PatientMemoryStore":
    """Build the configured durable patient-memory adapter.

    ``PATIENT_MEMORY_STORE_BACKEND=memory`` is the safe development default.
    Redis is selected explicitly and reuses ``REDIS_URL``.
    """
    backend = os.getenv("PATIENT_MEMORY_STORE_BACKEND", "memory").lower()
    if backend == "redis":
        return RedisPatientMemoryStore(
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0")
        )
    if backend != "memory":
        raise ValueError(f"Unsupported patient memory backend: {backend}")
    return InMemoryPatientMemoryStore()


# ── Durable patient memory ───────────────────────────────────────────────────


@dataclass
class PatientMemoryFact:
    """A governed longitudinal fact associated with one patient.

    ``value`` is intentionally typed as ``str``: durable memory stores a
    minimized representation rather than raw clinical documents.  Callers may
    retain a stable ``fact_id`` for idempotent writes and provenance audits.
    """

    key: str
    value: str
    fact_id: str | None = None
    category: str = "clinical"
    source: str = ""
    source_type: str = "unknown"
    observed_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> "PatientMemoryFact":
        """Return a normalized, PHI-minimized copy suitable for persistence."""
        key = " ".join(self.key.strip().lower().split())[:128]
        value = " ".join(self.value.strip().split())[:1000]
        metadata = {
            str(k): str(v)[:256]
            for k, v in self.metadata.items()
            if str(k).lower() not in {"name", "address", "phone", "email", "ssn"}
        }
        return PatientMemoryFact(
            key=key,
            value=value,
            fact_id=self.fact_id,
            category=" ".join(self.category.strip().lower().split())[:64] or "clinical",
            source=self.source.strip()[:256],
            source_type=self.source_type.strip().lower()[:64] or "unknown",
            observed_at=self.observed_at,
            expires_at=self.expires_at,
            confidence=max(0.0, min(float(self.confidence), 1.0)),
            metadata=metadata,
        )

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at <= time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "fact_id": self.fact_id,
            "category": self.category,
            "source": self.source,
            "source_type": self.source_type,
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PatientMemoryFact":
        return cls(
            key=str(data.get("key", "")),
            value=str(data.get("value", "")),
            fact_id=data.get("fact_id"),
            category=str(data.get("category", "clinical")),
            source=str(data.get("source", "")),
            source_type=str(data.get("source_type", "unknown")),
            observed_at=float(data.get("observed_at", time.time())),
            expires_at=data.get("expires_at"),
            confidence=float(data.get("confidence", 1.0)),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class PatientMemoryPolicy:
    """Consent and retention policy for durable patient memory."""

    consent_required: bool = True
    consent_granted: bool = False
    retention_seconds: int = 30 * 24 * 60 * 60
    max_facts: int = 100
    allowed_categories: set[str] = field(default_factory=set)

    def evaluate(self, *, consent: bool | None = None, now: float | None = None) -> tuple[bool, str]:
        if self.consent_required and not (self.consent_granted if consent is None else consent):
            return False, "consent_denied"
        if self.retention_seconds <= 0:
            return False, "retention_disabled"
        return True, "allowed"


@dataclass
class PatientMemoryRecord:
    """Patient-scoped durable memory plus policy metadata."""

    patient_id: str
    facts: list[PatientMemoryFact] = field(default_factory=list)
    policy: PatientMemoryPolicy = field(default_factory=PatientMemoryPolicy)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def active_facts(self, *, now: float | None = None) -> list[PatientMemoryFact]:
        current = time.time() if now is None else now
        return [
            fact for fact in self.facts
            if (fact.expires_at is None or fact.expires_at > current)
            and current - fact.observed_at <= self.policy.retention_seconds
        ]

    def to_context(self) -> list[dict[str, Any]]:
        return [
            {
                **fact.to_dict(),
                "patient_id": self.patient_id,
                "memory_type": "durable_patient_memory",
                "trusted": True,
            }
            for fact in self.active_facts()
        ]


class PatientMemoryStore(Protocol):
    def load(self, patient_id: str) -> PatientMemoryRecord | None: ...
    def save(self, record: PatientMemoryRecord) -> None: ...
    def delete(self, patient_id: str) -> None: ...


class InMemoryPatientMemoryStore:
    """Provider-neutral development store with patient-ID isolation."""

    def __init__(self) -> None:
        self._records: dict[str, PatientMemoryRecord] = {}

    def load(self, patient_id: str) -> PatientMemoryRecord | None:
        record = self._records.get(patient_id)
        if record is None:
            return None
        active = record.active_facts()
        record.facts = active
        return record

    def save(self, record: PatientMemoryRecord) -> None:
        self._records[record.patient_id] = record

    def delete(self, patient_id: str) -> None:
        self._records.pop(patient_id, None)


class RedisPatientMemoryStore:
    """Redis-ready patient store; Redis is imported only when selected."""

    _KEY_PREFIX = "patient-memory:"

    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        try:
            import redis
        except ImportError as exc:
            raise ImportError("redis package required: pip install redis") from exc
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def _key(self, patient_id: str) -> str:
        return f"{self._KEY_PREFIX}{patient_id}"

    def load(self, patient_id: str) -> PatientMemoryRecord | None:
        data = self._client.get(self._key(patient_id))
        if data is None:
            return None
        obj = json.loads(data)
        policy_data = obj.get("policy", {})
        policy = PatientMemoryPolicy(
            consent_required=policy_data.get("consent_required", True),
            consent_granted=policy_data.get("consent_granted", False),
            retention_seconds=int(policy_data.get("retention_seconds", 30 * 24 * 60 * 60)),
            max_facts=int(policy_data.get("max_facts", 100)),
            allowed_categories=set(policy_data.get("allowed_categories", [])),
        )
        record = PatientMemoryRecord(
            patient_id=obj["patient_id"],
            facts=[PatientMemoryFact.from_dict(item) for item in obj.get("facts", [])],
            policy=policy,
            created_at=float(obj.get("created_at", time.time())),
            updated_at=float(obj.get("updated_at", time.time())),
            metadata=dict(obj.get("metadata") or {}),
        )
        record.facts = record.active_facts()
        return record

    def save(self, record: PatientMemoryRecord) -> None:
        payload = {
            "patient_id": record.patient_id,
            "facts": [fact.to_dict() for fact in record.facts],
            "policy": {
                "consent_required": record.policy.consent_required,
                "consent_granted": record.policy.consent_granted,
                "retention_seconds": record.policy.retention_seconds,
                "max_facts": record.policy.max_facts,
                "allowed_categories": sorted(record.policy.allowed_categories),
            },
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "metadata": record.metadata,
        }
        self._client.set(self._key(record.patient_id), json.dumps(payload))

    def delete(self, patient_id: str) -> None:
        self._client.delete(self._key(patient_id))
