from __future__ import annotations

from jsonschema import validate


REQUEST_SCHEMAS = {
    "patient_context_get": {
        "type": "object",
        "required": ["patient_id"],
        "properties": {
            "patient_id": {"type": "string", "minLength": 1},
            "include_claims": {"type": "boolean"},
            "include_interactions": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    "vector_evidence_search": {
        "type": "object",
        "required": ["question"],
        "properties": {
            "question": {"type": "string", "minLength": 3},
            "patient_id": {"type": ["string", "null"]},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "additionalProperties": False,
    },
    "graphrag_answer_generate": {
        "type": "object",
        "required": ["question"],
        "properties": {
            "question": {"type": "string", "minLength": 3},
            "patient_id": {"type": ["string", "null"]},
            "response_style": {
                "type": "string",
                "enum": ["concise", "clinical", "audit"],
            },
        },
        "additionalProperties": False,
    },
    "risk_summary_generate": {
        "type": "object",
        "required": ["patient_id"],
        "properties": {
            "patient_id": {"type": "string", "minLength": 1},
            "time_window_hours": {
                "type": "integer",
                "minimum": 1,
                "maximum": 720,
            },
        },
        "additionalProperties": False,
    },
    "evidence_bundle_export": {
        "type": "object",
        "required": ["question"],
        "properties": {
            "question": {"type": "string", "minLength": 3},
            "patient_id": {"type": ["string", "null"]},
            "include_raw_payload": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
}


RESPONSE_SCHEMAS = {
    "patient_context_get": {
        "type": "object",
        "required": ["patient_id", "graph_context", "retrieved_at"],
        "properties": {
            "patient_id": {"type": "string"},
            "graph_context": {"type": "array", "items": {"type": "object"}},
            "retrieved_at": {"type": "string"},
            "trace_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "vector_evidence_search": {
        "type": "object",
        "required": ["question", "vector_context", "retrieved_at"],
        "properties": {
            "question": {"type": "string"},
            "vector_context": {"type": "array", "items": {"type": "object"}},
            "retrieved_at": {"type": "string"},
            "trace_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "graphrag_answer_generate": {
        "type": "object",
        "required": ["answer", "vector_context", "graph_context", "retrieved_at"],
        "properties": {
            "answer": {"type": "string"},
            "patients": {"type": "array", "items": {"type": "string"}},
            "vector_context": {"type": "array", "items": {"type": "object"}},
            "graph_context": {"type": "array", "items": {"type": "object"}},
            "retrieved_at": {"type": "string"},
            "trace_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "risk_summary_generate": {
        "type": "object",
        "required": ["patient_id", "summary", "risk_signals", "retrieved_at"],
        "properties": {
            "patient_id": {"type": "string"},
            "summary": {"type": "string"},
            "risk_signals": {"type": "array", "items": {"type": "string"}},
            "retrieved_at": {"type": "string"},
            "trace_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    "evidence_bundle_export": {
        "type": "object",
        "required": ["question", "bundle", "retrieved_at"],
        "properties": {
            "question": {"type": "string"},
            "bundle": {
                "type": "object",
                "required": ["vector_evidence", "graph_evidence"],
                "properties": {
                    "vector_evidence": {"type": "array", "items": {"type": "object"}},
                    "graph_evidence": {"type": "array", "items": {"type": "object"}},
                },
                "additionalProperties": True,
            },
            "retrieved_at": {"type": "string"},
            "trace_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
}


def validate_request(tool_name: str, payload: dict) -> None:
    validate(instance=payload, schema=REQUEST_SCHEMAS[tool_name])


def validate_response(tool_name: str, payload: dict) -> None:
    validate(instance=payload, schema=RESPONSE_SCHEMAS[tool_name])
