import pytest
from pydantic import ValidationError

from supply_chain_agent.api import schemas
from supply_chain_agent.api.schemas import (
    EntityRequest,
    QueryRequest,
    RequestLimits,
    VectorEvidenceSearchRequest,
    configure_request_limits,
)


@pytest.fixture(autouse=True)
def _restore_limits():
    original = schemas.request_limits()
    yield
    configure_request_limits(original)


def test_strips_whitespace_and_defaults():
    request = VectorEvidenceSearchRequest(question="  late shipments  ", entity_id=" S-1 ")
    assert request.question == "late shipments"
    assert request.entity_id == "S-1"
    assert request.top_k == 5
    assert QueryRequest(question="abc").entity_id is None


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        QueryRequest(question="abc", other=1)


def test_entity_id_bounds():
    with pytest.raises(ValidationError):
        EntityRequest(entity_id="")
    with pytest.raises(ValidationError):
        QueryRequest(question="abc", entity_id="x" * 129)


def test_limits_read_at_validation_time():
    configure_request_limits(RequestLimits(max_question_chars=5, max_context_items=10))
    with pytest.raises(ValidationError, match="question must be at most 5 characters"):
        QueryRequest(question="x" * 6)
    assert VectorEvidenceSearchRequest(question="abc", top_k=10).top_k == 10
    with pytest.raises(ValidationError, match="top_k must be at most 10"):
        VectorEvidenceSearchRequest(question="abc", top_k=11)
