import json

from healthcare_agent.generation.structured_output import parse_structured_response


def _payload(**overrides):
    base = {
        "summary": "  Elevated bleeding risk.  ",
        "key_findings": ["Warfarin and aspirin co-prescribed"],
        "risks": [
            {
                "category": "drug_interaction",
                "severity": "HIGH",
                "description": "Additive anticoagulant effect",
                "evidence_source": " Graph_Fact ",
            }
        ],
        "confidence": 0.8,
    }
    base.update(overrides)
    return base


def test_parses_valid_json_and_normalizes_labels():
    result = parse_structured_response(json.dumps(_payload()))
    assert result.summary == "Elevated bleeding risk."
    assert result.risks[0].severity == "high"
    assert result.risks[0].evidence_source == "graph_fact"
    assert result.confidence == 0.8


def test_strips_markdown_code_fence():
    raw = "```json\n" + json.dumps(_payload()) + "\n```"
    assert parse_structured_response(raw).confidence == 0.8


def test_maps_severity_aliases():
    payload = _payload(interactions=[{"drug_a": "a", "drug_b": "b", "severity": "Severe"}])
    assert parse_structured_response(json.dumps(payload)).interactions[0].severity == "high"


def test_ignores_unknown_keys_and_truncates_oversized_values():
    payload = _payload(extra_field="x", key_findings=["f"] * 50, summary="s" * 5000)
    result = parse_structured_response(json.dumps(payload))
    assert len(result.key_findings) == 20
    assert len(result.summary) == 1000
    assert "extra_field" not in result.model_dump()


def test_invalid_output_degrades_to_low_confidence_fallback():
    result = parse_structured_response("not json at all")
    assert result.confidence == 0.1
    assert result.summary == "not json at all"
    assert result.key_findings == ["Unable to parse structured response from LLM"]


def test_out_of_range_confidence_falls_back():
    result = parse_structured_response(json.dumps(_payload(confidence=3)))
    assert result.confidence == 0.1


def test_dump_shape_is_stable():
    keys = set(parse_structured_response(json.dumps(_payload())).model_dump())
    assert keys == {
        "summary", "key_findings", "risks", "interactions",
        "lab_signals", "confidence", "safety_caveat",
    }
