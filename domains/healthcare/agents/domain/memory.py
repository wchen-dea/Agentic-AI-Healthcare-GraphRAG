"""Conversation memory and session management.

Provides a lightweight session store for multi-turn conversations,
enabling context carryover and user preference learning.
"""
from __future__ import annotations

import time
import hashlib
from collections import deque
from dataclasses import dataclass, field
from typing import Any


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


# Singleton store
_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store
