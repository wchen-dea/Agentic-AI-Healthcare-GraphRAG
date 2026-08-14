from __future__ import annotations

import json
from typing import Any

from .graph_writes import (
    merge_base_event,
    merge_disruption_alert,
    merge_facility_reference,
    merge_inventory_level,
    merge_part_reference,
    merge_purchase_order,
    merge_quality_result,
    merge_shipment,
    merge_supplier_reference,
)


def clinical_text(event: dict) -> str:
    """Build searchable text from a supply-chain event."""
    payload = json.loads(event.get("payload_json", "{}"))
    event_type = event.get("event_type", "")
    parts: list[str] = []

    if event_type == "PURCHASE_ORDER":
        parts.append(f"Purchase order {payload.get('po_number')} from supplier {payload.get('supplier_id')} "
                      f"for part {payload.get('part_name', payload.get('part_id'))} qty {payload.get('quantity')} "
                      f"status {payload.get('status')}.")
    elif event_type == "SHIPMENT_UPDATE":
        parts.append(f"Shipment {payload.get('shipment_id')} via {payload.get('transport_mode')} "
                      f"from {payload.get('origin_facility')} to {payload.get('destination_facility')} "
                      f"status {payload.get('status')} lead {payload.get('actual_lead_days')}d "
                      f"(expected {payload.get('expected_lead_days')}d).")
    elif event_type == "QUALITY_RESULT":
        parts.append(f"Quality inspection {payload.get('inspection_id')} for part {payload.get('part_id')} "
                      f"result {payload.get('result')} defect_rate {payload.get('defect_rate')}.")
    elif event_type == "DISRUPTION_ALERT":
        parts.append(f"Disruption {payload.get('disruption_type')} at {payload.get('facility_id')} "
                      f"severity {payload.get('severity')} region {payload.get('region')}. "
                      f"{payload.get('description', '')}")
    elif event_type == "INVENTORY_LEVEL":
        parts.append(f"Inventory at {payload.get('facility_id')} part {payload.get('part_id')} "
                      f"on_hand {payload.get('on_hand_qty')} "
                      f"{'BELOW REORDER' if payload.get('below_reorder') else 'ok'} "
                      f"days_of_supply {payload.get('days_of_supply')}.")
    elif event_type in ("SUPPLIER_MASTER_UPSERT", "PART_MASTER_UPSERT", "FACILITY_MASTER_UPSERT"):
        parts.append(f"Reference update {event_type}: {json.dumps(payload)[:200]}")
    else:
        parts.append(f"Supply chain event {event_type}: {json.dumps(payload)[:200]}")

    return " ".join(parts)


class SupplyChainPipelineService:
    def __init__(self, neo4j_driver, qdrant_client, qdrant_collection, embed_fn):
        self.neo4j = neo4j_driver
        self.qdrant = qdrant_client
        self.qdrant_collection = qdrant_collection
        self.embed_fn = embed_fn

    def process_event(self, event: dict[str, Any]) -> None:
        payload = json.loads(event.get("payload_json", "{}"))
        text = clinical_text(event)
        vector = self.embed_fn(text)

        self._write_qdrant(event, payload, text, vector)
        self._write_neo4j(event, payload, text)

    def _write_qdrant(self, event, payload, text, vector):
        from qdrant_client.models import PointStruct
        import hashlib
        point_id = int(hashlib.md5(event["event_id"].encode()).hexdigest()[:16], 16)
        self.qdrant.upsert(
            collection_name=self.qdrant_collection,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "event_id": event["event_id"],
                    "event_ts": event["event_ts"],
                    "event_type": event["event_type"],
                    "entity_id": event.get("entity_id"),
                    "facility_id": event.get("facility_id"),
                    "supplier_id": event.get("supplier_id"),
                    "source_system": event.get("source_system"),
                    "text": text,
                },
            )],
        )

    def _write_neo4j(self, event, payload, text):
        with self.neo4j.session() as session:
            session.execute_write(merge_base_event, event, text)
            et = event["event_type"]
            if et == "PURCHASE_ORDER":
                session.execute_write(merge_purchase_order, event, payload)
            elif et == "SHIPMENT_UPDATE":
                session.execute_write(merge_shipment, event, payload)
            elif et == "QUALITY_RESULT":
                session.execute_write(merge_quality_result, event, payload)
            elif et == "DISRUPTION_ALERT":
                session.execute_write(merge_disruption_alert, event, payload)
            elif et == "INVENTORY_LEVEL":
                session.execute_write(merge_inventory_level, event, payload)
            elif et == "SUPPLIER_MASTER_UPSERT":
                session.execute_write(merge_supplier_reference, event, payload)
            elif et == "PART_MASTER_UPSERT":
                session.execute_write(merge_part_reference, event, payload)
            elif et == "FACILITY_MASTER_UPSERT":
                session.execute_write(merge_facility_reference, event, payload)
