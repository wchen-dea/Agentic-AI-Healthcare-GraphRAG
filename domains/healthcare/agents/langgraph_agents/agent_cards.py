"""Agent capability cards and delegation protocol for inter-agent communication.

Enables typed, auditable delegation between LangGraph agent nodes without
network hops. Each agent declares its capabilities via an AgentCard; agents
emit DelegationRequest messages that the delegation router resolves by
invoking the target agent and appending a DelegationResponse to state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentCard:
    name: str
    capabilities: tuple[str, ...]
    accepted_inputs: tuple[str, ...]
    description: str = ""

    def can_handle(self, capability: str) -> bool:
        return capability in self.capabilities


AGENT_REGISTRY: dict[str, AgentCard] = {
    "triage": AgentCard(
        name="triage",
        capabilities=("classify", "plan"),
        accepted_inputs=("question", "patient_id"),
        description="Classifies query intent and produces retrieval plan",
    ),
    "vector_retrieval": AgentCard(
        name="vector_retrieval",
        capabilities=("vector_search", "semantic_similarity"),
        accepted_inputs=("question", "patient_id", "top_k"),
        description="Runs vector similarity search against Qdrant",
    ),
    "graph_retrieval": AgentCard(
        name="graph_retrieval",
        capabilities=("graph_search", "patient_context"),
        accepted_inputs=("patient_ids",),
        description="Queries Neo4j patient graph",
    ),
    "medication_safety": AgentCard(
        name="medication_safety",
        capabilities=("drug_interaction", "contraindication", "adverse_reaction", "polypharmacy"),
        accepted_inputs=("graph_context", "patient_id"),
        description="Assesses drug interactions, contraindications, and adverse reactions",
    ),
    "lab_interpretation": AgentCard(
        name="lab_interpretation",
        capabilities=("lab_signal", "abnormal_detection", "trend_analysis", "renal_function", "hepatic_function"),
        accepted_inputs=("graph_context", "patient_id"),
        description="Interprets lab signals and abnormal observations",
    ),
    "coding_review": AgentCard(
        name="coding_review",
        capabilities=("icd10_gap", "claim_review", "denial_prevention"),
        accepted_inputs=("graph_context", "patient_id"),
        description="Reviews claims, coding gaps, and ICD-10 mapping",
    ),
    "synthesis": AgentCard(
        name="synthesis",
        capabilities=("answer_generation", "evidence_grounding"),
        accepted_inputs=("question", "vector_context", "graph_context", "messages"),
        description="Generates grounded clinical answer from evidence",
    ),
}


@dataclass
class DelegationRequest:
    from_agent: str
    to_agent: str
    capability: str
    query: str
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "delegation_request",
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "capability": self.capability,
            "query": self.query,
            "context": self.context,
        }


@dataclass
class DelegationResponse:
    from_agent: str
    to_agent: str
    capability: str
    result: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "delegation_response",
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "capability": self.capability,
            "result": self.result,
            "confidence": self.confidence,
        }


def discover_agents(capability: str) -> list[AgentCard]:
    """Find agents that can handle a given capability."""
    return [card for card in AGENT_REGISTRY.values() if card.can_handle(capability)]


def resolve_delegation(request: DelegationRequest) -> str | None:
    """Return the target agent name if valid, None otherwise."""
    card = AGENT_REGISTRY.get(request.to_agent)
    if card and card.can_handle(request.capability):
        return request.to_agent
    candidates = discover_agents(request.capability)
    return candidates[0].name if candidates else None
