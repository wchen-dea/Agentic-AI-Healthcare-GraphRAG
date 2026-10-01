from dataclasses import dataclass
from typing import Literal


RequestType = Literal[
    "patient_summary",
    "medication_safety",
    "lab_interpretation",
    "coding_review",
    "cohort_triage",
]


@dataclass(frozen=True)
class RetrievalPlan:
    name: RequestType
    query_text: str
    top_k: int
    reason: str
