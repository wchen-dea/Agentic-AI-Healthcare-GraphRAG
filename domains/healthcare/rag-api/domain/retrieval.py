"""Vector and graph retrieval services.

Extracted from app.py to break circular imports from langgraph_agents
and provide a single retrieval interface for all orchestration modes.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any


VECTOR_SIZE = 384
_EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
    except Exception:
        _embedding_model = False
    return _embedding_model


def stable_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    model = _get_embedding_model()
    if model and model is not False:
        vec = model.encode(text, normalize_embeddings=True).tolist()
        return vec[:dim] if len(vec) >= dim else vec + [0.0] * (dim - len(vec))
    vec = [0.0] * dim
    for token in text.lower().split():
        token_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[token_hash % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def vector_search(
    qdrant_client,
    collection: str,
    question: str,
    patient_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    query_vector = stable_embedding(question)
    query_filter = None
    if patient_id:
        query_filter = {"must": [{"key": "patient_id", "match": {"value": patient_id}}]}

    results = qdrant_client.search(
        collection_name=collection,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=limit,
    )
    return [
        {
            "score": result.score,
            "event_id": result.payload.get("event_id"),
            "patient_id": result.payload.get("patient_id"),
            "event_type": result.payload.get("event_type"),
            "text": result.payload.get("text"),
        }
        for result in results
    ]


_GRAPH_QUERY = """
MATCH (p:Patient)
WHERE p.id IN $patient_ids

    CALL (p) {
        OPTIONAL MATCH (p)-[hc:HAS_CONDITION]->(c:Condition)
        RETURN collect(DISTINCT {name: c.name, onset_ts: toString(hc.onset_ts)})[..20] AS conditions
    }

    CALL (p) {
        OPTIONAL MATCH (p)-[:HAS_SYMPTOM]->(s:Symptom)
        RETURN collect(DISTINCT s.name)[..20] AS symptoms
    }

    CALL (p) {
        OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)
        RETURN collect(
            DISTINCT {name: o.name, value: o.value, unit: o.unit, abnormal: o.abnormal, panel: o.lab_panel, specimen: o.specimen_type, event_ts: toString(o.event_ts)}
        )[..20] AS observations
    }

    CALL (p) {
        OPTIONAL MATCH (p)-[:HAS_MEDICATION_ORDER]->(mo:MedicationOrder)-[:ORDERS_MEDICATION]->(m:Medication)
        RETURN collect(
            DISTINCT {medication: m.name, drug_class: m.drug_class, dose: mo.dose, route: mo.route, frequency: mo.frequency, order_type: mo.order_type, order_ts: toString(mo.event_ts)}
        )[..20] AS medications
    }

    CALL (p) {
        OPTIONAL MATCH (p)-[:HAS_MEDICATION_ORDER]->(mo:MedicationOrder)-[:ORDERS_MEDICATION]->(m:Medication)
        WHERE NOT mo.order_type IN $excluded_order_types
        OPTIONAL MATCH (m)-[i:INTERACTS_WITH]->(m2:Medication)
        WITH m, i, m2 WHERE i IS NOT NULL
        RETURN collect(
            DISTINCT {from: m.name, to: m2.name, risk: i.risk, severity: i.severity}
        )[..20] AS interactions
    }

    CALL (p) {
        OPTIONAL MATCH (p)-[:HAS_DEVICE_READING]->(dr:DeviceReading)
        RETURN collect(
            DISTINCT {
                heart_rate: dr.heart_rate,
                spo2: dr.spo2,
                bp: toString(dr.systolic_bp) + '/' + toString(dr.diastolic_bp),
                temp_c: dr.temperature_c,
                rr: dr.respiratory_rate,
                alert: dr.alert
            }
        )[..20] AS vitals
    }

    CALL (p) {
        OPTIONAL MATCH (p)-[:HAS_CLAIM]->(cl:Claim)
        OPTIONAL MATCH (cl)-[:SUBMITTED_TO]->(pay:Payer)
        OPTIONAL MATCH (cl)-[:FOR_PROCEDURE]->(proc:Procedure)
        RETURN collect(
            DISTINCT {payer: coalesce(pay.name, cl.payer), code: proc.code, description: proc.description, status: cl.status, claim_type: cl.claim_type, billed: cl.billed_amount}
        )[..20] AS claims
    }

    CALL (p) {
        OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)-[mi:MAY_INDICATE]->(c:Condition)
        RETURN collect(
            DISTINCT {observation: o.name, value: o.value, unit: o.unit, indicated_condition: c.name, reason: mi.reason}
        )[..20] AS lab_signals
    }

    CALL (p) {
        OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)-[:CODED_AS]->(icd:ICD10Code)
        RETURN collect(DISTINCT {condition: c.name, icd10: icd.code})[..20] AS icd10_codes
    }

    CALL (p) {
        OPTIONAL MATCH (p)-[:REPORTED_ADVERSE_REACTION]->(ae:AdverseEvent)-[:ASSOCIATED_WITH_MEDICATION]->(m:Medication)
        WITH ae, m WHERE ae IS NOT NULL
        RETURN collect(
            DISTINCT {symptom: ae.symptom_name, medication: m.name, severity: ae.severity, meddra_term: ae.meddra_term}
        )[..20] AS adverse_events
    }

    CALL (p) {
        OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)<-[ci:CONTRAINDICATED_FOR]-(m:Medication)
        WHERE EXISTS { MATCH (p)-[:HAS_MEDICATION_ORDER]->(mo:MedicationOrder)-[:ORDERS_MEDICATION]->(m) WHERE NOT mo.order_type IN $excluded_order_types }
        RETURN collect(
            DISTINCT {medication: m.name, condition: c.name, reason: ci.reason, severity: ci.severity}
        )[..10] AS contraindications
    }

RETURN p.id AS patient_id,
                 p.age AS age,
                 p.sex AS sex,
                 p.risk_tier AS risk_tier,
                 conditions,
                 symptoms,
                 observations,
                 medications,
                 interactions,
                 vitals,
                 claims,
                 lab_signals,
                 icd10_codes,
                 adverse_events,
                 contraindications
"""


def graph_search(neo4j_driver, patient_ids: list[str]) -> list[dict[str, Any]]:
    with neo4j_driver.session() as session:
        records = session.run(
            _GRAPH_QUERY,
            {"patient_ids": patient_ids, "excluded_order_types": ["discontinued", "hold"]},
        )
        return [dict(record) for record in records]
