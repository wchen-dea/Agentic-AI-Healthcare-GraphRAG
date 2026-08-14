from .models import RequestType, RetrievalPlan


def _bounded_top_k(max_top_k: int, *, cap: int) -> int:
    return max(1, min(max_top_k, cap))


def classify_request_type(question: str, patient_id: str | None) -> RequestType:
    text = question.lower()

    if any(token in text for token in ["contraindication", "interaction", "adverse", "medication"]):
        return "medication_safety"
    if any(token in text for token in ["potassium", "lab", "observation", "vital"]):
        return "lab_interpretation"
    if any(token in text for token in ["claim", "coding", "icd", "cpt", "denial"]):
        return "coding_review"
    if any(token in text for token in ["cohort", "population", "across patients"]) or not patient_id:
        return "cohort_triage"
    return "patient_summary"


def select_retrieval_plan(
    request_type: RequestType,
    question: str,
    patient_id: str | None,
    max_top_k: int,
) -> RetrievalPlan:
    max_top_k = max(1, max_top_k)

    if request_type == "medication_safety":
        return RetrievalPlan(
            name=request_type,
            query_text=f"Medication safety focus: {question}",
            top_k=_bounded_top_k(max_top_k, cap=6),
            reason="Question contains medication safety semantics.",
        )
    if request_type == "lab_interpretation":
        return RetrievalPlan(
            name=request_type,
            query_text=f"Lab interpretation focus: {question}",
            top_k=_bounded_top_k(max_top_k, cap=6),
            reason="Question contains lab or observation semantics.",
        )
    if request_type == "coding_review":
        return RetrievalPlan(
            name=request_type,
            query_text=f"Coding and claims focus: {question}",
            top_k=_bounded_top_k(max_top_k, cap=6),
            reason="Question contains coding or claims semantics.",
        )
    if request_type == "cohort_triage":
        scope_hint = "cohort" if not patient_id else "patient plus cohort"
        bounded = _bounded_top_k(max_top_k, cap=8)
        preferred = max(3, bounded)
        return RetrievalPlan(
            name=request_type,
            query_text=f"Cohort triage focus ({scope_hint}): {question}",
            top_k=min(max_top_k, preferred),
            reason="Question implies cohort-level triage or lacks explicit patient scope.",
        )
    return RetrievalPlan(
        name="patient_summary",
        query_text=question,
        top_k=_bounded_top_k(max_top_k, cap=5),
        reason="Default patient summary path.",
    )
