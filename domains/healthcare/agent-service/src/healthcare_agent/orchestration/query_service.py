"""Application service for question answering over the LangGraph orchestrator.

Owns request-level concerns that sit around the graph: the evidence budget
(``context_limit``) and conversation memory. Transport layers (HTTP routes,
MCP tools, evaluation gates) call this service instead of the graph directly.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Literal

from healthcare_agent.orchestration.memory import (
    InMemoryPatientMemoryStore,
    PatientMemoryFact,
    PatientMemoryPolicy,
    PatientMemoryRecord,
    PatientMemoryStore,
    get_session_store,
)
from healthcare_agent.orchestration.orchestrator import LangGraphOrchestrator


class QueryService:
    def __init__(
        self,
        *,
        max_context_items: int,
        orchestrator: LangGraphOrchestrator | None = None,
        patient_memory_store: PatientMemoryStore | None = None,
    ) -> None:
        self._max_context_items = max_context_items
        self._orchestrator = orchestrator or LangGraphOrchestrator.build()
        self._patient_memory_store = patient_memory_store or InMemoryPatientMemoryStore()

    def context_limit(self, top_k: int | None) -> int:
        return min(top_k or self._max_context_items, max(self._max_context_items, 8))

    @staticmethod
    def load_session_context(session_id: str | None) -> str:
        if not session_id:
            return ""
        return get_session_store().get_or_create(session_id).get_context_summary()

    def load_patient_memory(self, patient_id: str | None) -> PatientMemoryRecord | None:
        """Load only active, patient-scoped durable facts."""
        if not patient_id:
            return None
        return self._patient_memory_store.load(patient_id)

    def evaluate_retention_and_consent(
        self,
        policy: PatientMemoryPolicy | None = None,
        *,
        consent: bool | None = None,
        now: float | None = None,
    ) -> tuple[bool, str]:
        """Evaluate policy before any durable-memory write."""
        return (policy or PatientMemoryPolicy()).evaluate(consent=consent, now=now)

    def write_patient_memory(
        self,
        patient_id: str,
        facts: list[PatientMemoryFact | dict[str, Any]],
        provenance: dict[str, Any] | str,
        consent: bool,
        *,
        policy: PatientMemoryPolicy | None = None,
    ) -> PatientMemoryRecord:
        """Persist normalized, minimized facts only after governance checks."""
        if not patient_id.strip():
            raise ValueError("patient_id is required")
        active_policy = policy or PatientMemoryPolicy(consent_granted=consent)
        allowed, reason = self.evaluate_retention_and_consent(
            active_policy, consent=consent
        )
        if not allowed:
            raise PermissionError(reason)

        normalized: list[PatientMemoryFact] = []
        for raw_fact in facts:
            fact = raw_fact if isinstance(raw_fact, PatientMemoryFact) else PatientMemoryFact.from_dict(raw_fact)
            fact = fact.normalized()
            fact.metadata = {**fact.metadata, "provenance": provenance}
            if active_policy.allowed_categories and fact.category not in active_policy.allowed_categories:
                continue
            if not fact.key or not fact.value or fact.is_expired:
                continue
            normalized.append(fact)

        existing = self._patient_memory_store.load(patient_id)
        record = existing or PatientMemoryRecord(patient_id=patient_id, policy=active_policy)
        record.policy = active_policy
        merged: dict[str, PatientMemoryFact] = {
            (fact.fact_id or f"{fact.category}:{fact.key}"): fact
            for fact in record.active_facts()
        }
        for fact in normalized:
            merged[fact.fact_id or f"{fact.category}:{fact.key}"] = fact
        record.facts = list(merged.values())[-active_policy.max_facts:]
        record.updated_at = __import__("time").time()
        record.metadata["last_write_provenance"] = provenance
        self._patient_memory_store.save(record)
        return record

    @staticmethod
    def remember_turn(
        session_id: str | None, question: str, result: dict[str, Any], patient_id: str | None
    ) -> None:
        if not session_id or (result.get("guardrails") or {}).get("input_blocked"):
            return
        if result.get("status") == "pending_approval":
            # Only reviewed, final answers enter multi-turn memory.
            return
        store = get_session_store()
        session = store.get_or_create(session_id)
        session.add_turn(question=question, answer=result.get("answer", ""), patient_id=patient_id)
        save = getattr(store, "save", None)
        if callable(save):
            save(session)

    def run_query(
        self,
        question: str,
        patient_id: str | None = None,
        top_k: int | None = None,
        structured: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result = self._orchestrator.run(
            question=question,
            patient_id=patient_id,
            structured=structured,
            session_context=self.load_session_context(session_id),
            patient_memory=self.load_patient_memory(patient_id),
            context_limit=self.context_limit(top_k),
        )
        self.remember_turn(session_id, question, result, patient_id)
        return result

    def stream(
        self,
        question: str,
        patient_id: str | None = None,
        *,
        structured: bool = False,
        session_id: str | None = None,
        top_k: int | None = None,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield graph ``step`` events, then the ``result``; the turn is remembered on result."""
        for kind, data in self._orchestrator.stream(
            question,
            patient_id,
            structured=structured,
            session_context=self.load_session_context(session_id),
            patient_memory=self.load_patient_memory(patient_id),
            context_limit=self.context_limit(top_k),
        ):
            if kind == "result":
                self.remember_turn(session_id, question, data, patient_id)
            yield kind, data

    def pending_review(self, thread_id: str) -> dict[str, Any] | None:
        """Interrupt payload (question, patient_id, reason, ...) for a paused thread."""
        return self._orchestrator.pending(thread_id)

    def resume(
        self,
        thread_id: str,
        decision: Literal["approve", "reject"],
        *,
        note: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Apply a reviewer decision to a paused run; remembers the final turn.

        Raises ``KeyError`` for unknown or already-resolved threads.
        """
        pending = self._orchestrator.pending(thread_id)
        if pending is None:
            raise KeyError(thread_id)
        result = self._orchestrator.resume(thread_id, decision, note)
        self.remember_turn(
            session_id, str(pending.get("question") or ""), result, pending.get("patient_id")
        )
        return result
