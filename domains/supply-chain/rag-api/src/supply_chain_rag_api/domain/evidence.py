"""Evidence ranking for supply-chain queries."""
from typing import Any

from .models import RequestType


def rank_vector_context(
    items: list[dict[str, Any]],
    request_type: RequestType,
) -> list[dict[str, Any]]:
    event_priority = {
        "supplier_risk": {"supplier_event": 0, "risk_signal": 1},
        "shipment_tracking": {"shipment_event": 0, "logistics_alert": 1},
        "quality_review": {"inspection_event": 0, "defect_report": 1},
        "disruption_impact": {"disruption_alert": 0, "facility_event": 1},
        "inventory_planning": {"inventory_event": 0, "reorder_signal": 1},
        "procurement_overview": {"purchase_order": 0, "contract_event": 1},
    }
    priorities = event_priority.get(request_type, {})

    def _sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
        event_type = str(item.get("event_type") or "")
        priority = priorities.get(event_type, 99)
        score = float(item.get("score") or 0.0)
        event_id = str(item.get("event_id") or "")
        return (priority, -score, event_id)

    return sorted(items, key=_sort_key)


def rank_graph_context(
    items: list[dict[str, Any]],
    request_type: RequestType,
) -> list[dict[str, Any]]:
    return items
