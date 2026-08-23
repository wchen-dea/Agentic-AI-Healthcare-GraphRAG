from __future__ import annotations

from typing import Any


def merge_base_event(tx, event: dict[str, Any], text: str) -> None:
    tx.run(
        """
        MERGE (src:SourceSystem {name: $source_system})
          SET src.type = $source_type
        MERGE (ce:SupplyChainEvent {id: $event_id})
          SET ce.event_type = $event_type,
              ce.event_ts = datetime($event_ts),
              ce.text = $text,
              ce.schema_version = $schema_version
        MERGE (ce)-[:FROM_SOURCE]->(src)
        WITH ce
        CALL {
          WITH ce
          WITH ce WHERE $entity_id IS NOT NULL
          MERGE (p:Part {id: $entity_id})
          MERGE (ce)-[:ABOUT_PART]->(p)
          RETURN count(*) AS _
        }
        WITH ce
        CALL {
          WITH ce
          WITH ce WHERE $facility_id IS NOT NULL
          MERGE (f:Facility {id: $facility_id})
          MERGE (ce)-[:AT_FACILITY]->(f)
          RETURN count(*) AS _
        }
        WITH ce
        CALL {
          WITH ce
          WITH ce WHERE $supplier_id IS NOT NULL
          MERGE (s:Supplier {id: $supplier_id})
          MERGE (ce)-[:INVOLVES_SUPPLIER]->(s)
          RETURN count(*) AS _
        }
        RETURN ce
        """,
        {
            "source_system": event.get("source_system"),
            "source_type": event.get("source_type"),
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "event_ts": event.get("event_ts"),
            "text": text,
            "schema_version": event.get("schema_version"),
            "entity_id": event.get("entity_id"),
            "facility_id": event.get("facility_id"),
            "supplier_id": event.get("supplier_id"),
        },
    )


def merge_purchase_order(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (s:Supplier {id: $supplier_id})
        MERGE (p:Part {id: $part_id})
          SET p.name = coalesce($part_name, p.name),
              p.commodity_category = coalesce($commodity, p.commodity_category)
        MERGE (f:Facility {id: $facility_id})
        MERGE (po:PurchaseOrder {id: $po_number})
          SET po.quantity = $quantity,
              po.unit_price = $unit_price,
              po.total_value = $total_value,
              po.currency = $currency,
              po.incoterm = $incoterm,
              po.expected_delivery = $expected_delivery,
              po.status = $status,
              po.event_ts = datetime($event_ts)
        MERGE (po)-[:ORDERED_FROM]->(s)
        MERGE (po)-[:ORDERS_PART]->(p)
        MERGE (po)-[:DELIVERS_TO]->(f)
        MERGE (s)-[:SUPPLIES]->(p)
        """,
        {
            "supplier_id": payload.get("supplier_id"),
            "part_id": payload.get("part_id"),
            "part_name": payload.get("part_name"),
            "commodity": payload.get("commodity_category"),
            "facility_id": payload.get("destination_facility"),
            "po_number": payload.get("po_number"),
            "quantity": payload.get("quantity"),
            "unit_price": payload.get("unit_price"),
            "total_value": payload.get("total_value"),
            "currency": payload.get("currency"),
            "incoterm": payload.get("incoterm"),
            "expected_delivery": payload.get("expected_delivery_date"),
            "status": payload.get("status"),
            "event_ts": event["event_ts"],
        },
    )


def merge_shipment(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (s:Supplier {id: $supplier_id})
        MERGE (p:Part {id: $part_id})
        MERGE (origin:Facility {id: $origin})
        MERGE (dest:Facility {id: $destination})
        MERGE (sh:Shipment {id: $shipment_id})
          SET sh.transport_mode = $transport_mode,
              sh.carrier = $carrier,
              sh.container_id = $container_id,
              sh.status = $status,
              sh.expected_lead_days = $expected_lead_days,
              sh.actual_lead_days = $actual_lead_days,
              sh.quantity = $quantity,
              sh.weight_kg = $weight_kg,
              sh.customs_cleared = $customs_cleared,
              sh.event_ts = datetime($event_ts)
        MERGE (sh)-[:SHIPPED_FROM]->(origin)
        MERGE (sh)-[:SHIPPED_TO]->(dest)
        MERGE (sh)-[:CONTAINS_PART]->(p)
        MERGE (sh)-[:FROM_SUPPLIER]->(s)
        """,
        {
            "supplier_id": payload.get("supplier_id"),
            "part_id": payload.get("part_id"),
            "origin": payload.get("origin_facility"),
            "destination": payload.get("destination_facility"),
            "shipment_id": payload.get("shipment_id"),
            "transport_mode": payload.get("transport_mode"),
            "carrier": payload.get("carrier"),
            "container_id": payload.get("container_id"),
            "status": payload.get("status"),
            "expected_lead_days": payload.get("expected_lead_days"),
            "actual_lead_days": payload.get("actual_lead_days"),
            "quantity": payload.get("quantity"),
            "weight_kg": payload.get("weight_kg"),
            "customs_cleared": payload.get("customs_cleared"),
            "event_ts": event["event_ts"],
        },
    )


def merge_quality_result(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (s:Supplier {id: $supplier_id})
        MERGE (p:Part {id: $part_id})
        MERGE (f:Facility {id: $facility_id})
        MERGE (qi:QualityInspection {id: $inspection_id})
          SET qi.inspection_type = $inspection_type,
              qi.sample_size = $sample_size,
              qi.defects_found = $defects_found,
              qi.defect_rate = $defect_rate,
              qi.result = $result,
              qi.corrective_action_required = $car,
              qi.event_ts = datetime($event_ts)
        MERGE (qi)-[:INSPECTED_PART]->(p)
        MERGE (qi)-[:INSPECTED_AT]->(f)
        MERGE (qi)-[:SUPPLIED_BY]->(s)
        """,
        {
            "supplier_id": payload.get("supplier_id"),
            "part_id": payload.get("part_id"),
            "facility_id": payload.get("facility_id"),
            "inspection_id": payload.get("inspection_id"),
            "inspection_type": payload.get("inspection_type"),
            "sample_size": payload.get("sample_size"),
            "defects_found": payload.get("defects_found"),
            "defect_rate": payload.get("defect_rate"),
            "result": payload.get("result"),
            "car": payload.get("corrective_action_required"),
            "event_ts": event["event_ts"],
        },
    )


def merge_disruption_alert(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (f:Facility {id: $facility_id})
          SET f.region = coalesce($region, f.region),
              f.country = coalesce($country, f.country)
        MERGE (d:DisruptionEvent {id: $disruption_id})
          SET d.disruption_type = $disruption_type,
              d.severity = $severity,
              d.region = $region,
              d.country = $country,
              d.estimated_duration_days = $duration,
              d.description = $description,
              d.mitigation_status = $mitigation,
              d.event_ts = datetime($event_ts)
        MERGE (f)-[:DISRUPTED_BY]->(d)
        WITH d
        UNWIND $affected_parts AS part_id
        MERGE (p:Part {id: part_id})
        MERGE (d)-[:AFFECTS_PART]->(p)
        """,
        {
            "facility_id": payload.get("facility_id"),
            "disruption_id": payload.get("disruption_id"),
            "disruption_type": payload.get("disruption_type"),
            "severity": payload.get("severity"),
            "region": payload.get("region"),
            "country": payload.get("country"),
            "duration": payload.get("estimated_duration_days"),
            "description": payload.get("description"),
            "mitigation": payload.get("mitigation_status"),
            "affected_parts": payload.get("affected_parts", []),
            "event_ts": event["event_ts"],
        },
    )


def merge_inventory_level(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (f:Facility {id: $facility_id})
        MERGE (p:Part {id: $part_id})
        MERGE (f)-[inv:HOLDS_INVENTORY]->(p)
          SET inv.on_hand_qty = $on_hand,
              inv.allocated_qty = $allocated,
              inv.in_transit_qty = $in_transit,
              inv.reorder_point = $reorder_point,
              inv.below_reorder = $below_reorder,
              inv.days_of_supply = $days_of_supply,
              inv.updated_ts = datetime($event_ts)
        """,
        {
            "facility_id": payload.get("facility_id"),
            "part_id": payload.get("part_id"),
            "on_hand": payload.get("on_hand_qty"),
            "allocated": payload.get("allocated_qty"),
            "in_transit": payload.get("in_transit_qty"),
            "reorder_point": payload.get("reorder_point"),
            "below_reorder": payload.get("below_reorder"),
            "days_of_supply": payload.get("days_of_supply"),
            "event_ts": event["event_ts"],
        },
    )


def merge_supplier_reference(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (s:Supplier {id: $supplier_id})
          SET s.name = coalesce($name, s.name),
              s.country = coalesce($country, s.country),
              s.region = coalesce($region, s.region),
              s.tier = coalesce($tier, s.tier),
              s.risk_score = coalesce($risk_score, s.risk_score),
              s.iso_certified = coalesce($iso, s.iso_certified),
              s.geopolitical_risk = coalesce($geo_risk, s.geopolitical_risk)
        """,
        {
            "supplier_id": payload.get("supplier_id"),
            "name": payload.get("name"),
            "country": payload.get("country"),
            "region": payload.get("region"),
            "tier": payload.get("tier"),
            "risk_score": payload.get("risk_score"),
            "iso": payload.get("iso_certified"),
            "geo_risk": payload.get("geopolitical_risk"),
        },
    )


def merge_part_reference(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (p:Part {id: $part_id})
          SET p.name = coalesce($name, p.name),
              p.commodity_category = coalesce($commodity, p.commodity_category),
              p.criticality = coalesce($criticality, p.criticality),
              p.lead_time_days = coalesce($lead_time, p.lead_time_days),
              p.supplier_count = coalesce($supplier_count, p.supplier_count),
              p.single_source = coalesce($single_source, p.single_source)
        """,
        {
            "part_id": payload.get("part_id"),
            "name": payload.get("part_name"),
            "commodity": payload.get("commodity_category"),
            "criticality": payload.get("criticality"),
            "lead_time": payload.get("lead_time_days"),
            "supplier_count": payload.get("supplier_count"),
            "single_source": payload.get("single_source"),
        },
    )


def merge_facility_reference(tx, event: dict[str, Any], payload: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (f:Facility {id: $facility_id})
          SET f.name = coalesce($name, f.name),
              f.facility_type = coalesce($ftype, f.facility_type),
              f.country = coalesce($country, f.country),
              f.region = coalesce($region, f.region),
              f.capacity_utilization = coalesce($cap_util, f.capacity_utilization),
              f.operational_status = coalesce($op_status, f.operational_status)
        """,
        {
            "facility_id": payload.get("facility_id"),
            "name": payload.get("name"),
            "ftype": payload.get("facility_type"),
            "country": payload.get("country"),
            "region": payload.get("region"),
            "cap_util": payload.get("capacity_utilization"),
            "op_status": payload.get("operational_status"),
        },
    )
