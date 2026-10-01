"""Conversation memory and session management.

Provides pluggable session stores for multi-turn conversations:
- InMemorySessionStore (default): fast, no dependencies, lost on restart
- RedisSessionStore: persistent cross-session memory via Redis

Set SESSION_STORE_BACKEND=redis and REDIS_URL to enable Redis persistence.
"""
from __future__ import annotations

import json
import time
import hashlib
import os
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
