from .models import RequestType, RetrievalPlan


def classify_request_type(question: str, entity_id: str | None) -> RequestType:
    text = question.lower()
    if any(t in text for t in ["risk", "single source", "geopolitical", "exposure", "vulnerability"]):
        return "supplier_risk"
    if any(t in text for t in ["shipment", "transit", "delivery", "tracking", "delayed", "customs"]):
        return "shipment_tracking"
    if any(t in text for t in ["quality", "defect", "inspection", "rejection", "corrective"]):
        return "quality_review"
    if any(t in text for t in ["disruption", "shutdown", "closure", "strike", "disaster", "outage"]):
        return "disruption_impact"
    if any(t in text for t in ["inventory", "stock", "reorder", "days of supply", "shortage"]):
        return "inventory_planning"
    return "procurement_overview"


def select_retrieval_plan(
    request_type: RequestType,
    question: str,
    entity_id: str | None,
    max_top_k: int,
) -> RetrievalPlan:
    top_k = max(1, min(max_top_k, 8))

    prefixes = {
        "supplier_risk": "Supplier risk assessment focus:",
        "shipment_tracking": "Shipment and logistics focus:",
        "quality_review": "Quality inspection and defect focus:",
        "disruption_impact": "Disruption impact analysis focus:",
        "inventory_planning": "Inventory and reorder focus:",
        "procurement_overview": "Procurement overview:",
    }
    reasons = {
        "supplier_risk": "Question contains supplier risk semantics.",
        "shipment_tracking": "Question contains shipment or logistics semantics.",
        "quality_review": "Question contains quality or defect semantics.",
        "disruption_impact": "Question contains disruption or outage semantics.",
        "inventory_planning": "Question contains inventory or stock semantics.",
        "procurement_overview": "Default procurement overview path.",
    }

    prefix = prefixes.get(request_type, "")
    return RetrievalPlan(
        name=request_type,
        query_text=f"{prefix} {question}" if prefix else question,
        top_k=top_k,
        reason=reasons.get(request_type, "Default path."),
    )
