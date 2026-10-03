import pytest
from pydantic import ValidationError

from healthcare_agent.api import schemas
from healthcare_agent.api.schemas import (
    CodingGapDetectRequest,
    CohortRiskSummaryRequest,
    QueryRequest,
    RequestLimits,
    RiskSummaryRequest,
    VectorEvidenceSearchRequest,
    configure_request_limits,
)


@pytest.fixture(autouse=True)
def _restore_limits():
    original = schemas.request_limits()
    yield
    configure_request_limits(original)


def test_strips_whitespace_and_applies_defaults():
    request = QueryRequest(question="  what meds?  ")
    assert request.question == "what meds?"
    assert request.top_k == 5
    assert RiskSummaryRequest(patient_id="p1").time_window_hours == 72


def test_whitespace_only_question_rejected():
    with pytest.raises(ValidationError):
        QueryRequest(question="     ")


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        QueryRequest(question="what meds?", unexpected=True)


def test_requests_are_immutable():
    request = QueryRequest(question="what meds?")
    with pytest.raises(ValidationError):
        request.question = "changed"


def test_question_limit_is_read_at_validation_time():
    configure_request_limits(RequestLimits(max_question_chars=10))
    with pytest.raises(ValidationError, match="question must be at most 10 characters"):
        QueryRequest(question="x" * 11)


def test_top_k_capped_by_context_items():
    configure_request_limits(RequestLimits(max_context_items=3))
    assert VectorEvidenceSearchRequest(question="abc", top_k=3).top_k == 3
    with pytest.raises(ValidationError, match="top_k must be at most 3"):
        VectorEvidenceSearchRequest(question="abc", top_k=4)


def test_cohort_top_k_uses_cohort_cap():
    configure_request_limits(RequestLimits(max_context_items=3))
    assert CohortRiskSummaryRequest(question="abc", top_k=8).top_k == 8
    with pytest.raises(ValidationError, match="top_k must be at most 8"):
        CohortRiskSummaryRequest(question="abc", top_k=9)


def test_coding_gap_has_default_question_and_requires_patient():
    assert CodingGapDetectRequest(patient_id="p1").question
    with pytest.raises(ValidationError):
        CodingGapDetectRequest(patient_id="")


def test_time_window_bounds():
    with pytest.raises(ValidationError):
        RiskSummaryRequest(patient_id="p1", time_window_hours=721)
