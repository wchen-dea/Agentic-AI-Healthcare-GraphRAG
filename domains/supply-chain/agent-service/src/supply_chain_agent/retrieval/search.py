"""Vector (Qdrant) and graph (Neo4j) retrieval for supply-chain entities.

Clients are injected by the composition root so this module stays free of
service wiring and can be reused by agents, tools, and evaluation.
"""
from __future__ import annotations

from typing import Any

from supply_chain_agent.retrieval.embedding import stable_embedding

GRAPH_QUERY = """
UNWIND $ids AS eid
OPTIONAL MATCH (s:Supplier {id: eid})
OPTIONAL MATCH (p:Part {id: eid})
OPTIONAL MATCH (f:Facility {id: eid})
WITH coalesce(s, p, f) AS entity, eid
WHERE entity IS NOT NULL

CALL (entity) {
    OPTIONAL MATCH (entity)-[:SUPPLIES]->(part:Part)
    RETURN collect(DISTINCT {part_id: part.id, name: part.name, criticality: part.criticality})[..10] AS supplied_parts
}
CALL (entity) {
    OPTIONAL MATCH (entity)-[:HAS_RISK_SIGNAL]->(r:RiskSignal)
    RETURN collect(DISTINCT {category: r.category, description: r.description})[..10] AS risk_signals
}
CALL (entity) {
    OPTIONAL MATCH (entity)-[:DISRUPTED_BY]->(d:DisruptionEvent)
    RETURN collect(DISTINCT {type: d.disruption_type, severity: d.severity,
                             duration_days: d.estimated_duration_days,
                             mitigation: d.mitigation_status})[..10] AS disruptions
}
CALL (entity) {
    OPTIONAL MATCH (qi:QualityInspection)-[:SUPPLIED_BY]->(entity)
    WITH qi WHERE qi IS NOT NULL
    RETURN collect(DISTINCT {result: qi.result, defect_rate: qi.defect_rate, part_id: qi.part_id})[..10]
           AS quality_inspections
}
CALL (entity) {
    OPTIONAL MATCH (entity)-[inv:HOLDS_INVENTORY]->(part:Part)
    RETURN collect(DISTINCT {part_id: part.id, on_hand: inv.on_hand_qty, below_reorder: inv.below_reorder,
                             days_of_supply: inv.days_of_supply})[..10] AS inventory
}

RETURN eid AS entity_id, labels(entity)[0] AS entity_type,
       entity.name AS name, entity.country AS country, entity.region AS region,
       entity.risk_score AS risk_score, entity.geopolitical_risk AS geo_risk,
       entity.criticality AS criticality, entity.facility_type AS facility_type,
       supplied_parts, risk_signals, disruptions, quality_inspections, inventory
"""


def entity_filter(entity_id: str | None) -> dict[str, Any] | None:
    """Match an entity id against any of the id fields carried by event payloads."""
    if not entity_id:
        return None
    return {
        "should": [
            {"key": key, "match": {"value": entity_id}}
            for key in ("entity_id", "supplier_id", "facility_id")
        ]
    }


def vector_search(
    qdrant_client: Any, collection: str, question: str, entity_id: str | None, limit: int
) -> list[dict[str, Any]]:
    results = qdrant_client.search(
        collection_name=collection,
        query_vector=stable_embedding(question),
        query_filter=entity_filter(entity_id),
        limit=limit,
    )
    return [
        {
            "score": hit.score,
            "event_id": hit.payload.get("event_id"),
            "entity_id": hit.payload.get("entity_id"),
            "event_type": hit.payload.get("event_type"),
            "text": hit.payload.get("text"),
        }
        for hit in results
    ]


def graph_search(neo4j_driver: Any, entity_ids: list[str]) -> list[dict[str, Any]]:
    if not entity_ids:
        return []
    with neo4j_driver.session() as session:
        return [dict(record) for record in session.run(GRAPH_QUERY, {"ids": entity_ids})]
