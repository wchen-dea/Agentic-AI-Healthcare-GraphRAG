from dataclasses import dataclass
from typing import Literal

RequestType = Literal[
    "supplier_risk",
    "shipment_tracking",
    "quality_review",
    "disruption_impact",
    "inventory_planning",
    "procurement_overview",
]


@dataclass(frozen=True)
class RetrievalPlan:
    name: RequestType
    query_text: str
    top_k: int
    reason: str
