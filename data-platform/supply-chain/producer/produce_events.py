import json
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests
from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from faker import Faker

fake = Faker()

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092,localhost:9093,localhost:9094")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")
INTERVAL = float(os.getenv("EVENT_INTERVAL_SECONDS", "1"))
TX_EVENTS_PER_INTERVAL = max(0, int(os.getenv("TRANSACTION_EVENTS_PER_INTERVAL", "3")))
REF_EVENTS_PER_INTERVAL = max(0, int(os.getenv("REFERENCE_EVENTS_PER_INTERVAL", "3")))
SCHEMA_REGISTRY_STARTUP_TIMEOUT = int(os.getenv("SCHEMA_REGISTRY_STARTUP_TIMEOUT_SECONDS", "120"))
SCHEMA_REGISTRY_RETRY_INTERVAL = float(os.getenv("SCHEMA_REGISTRY_RETRY_INTERVAL_SECONDS", "3"))
SUPPLIER_POOL = max(20, int(os.getenv("SUPPLIER_POOL_SIZE", "200")))
FACILITY_POOL = max(10, int(os.getenv("FACILITY_POOL_SIZE", "100")))
PART_POOL = max(50, int(os.getenv("PART_POOL_SIZE", "500")))
LATE_EVENT_PROBABILITY = min(max(float(os.getenv("LATE_EVENT_PROBABILITY", "0.10")), 0.0), 1.0)

producer = Producer({"bootstrap.servers": BOOTSTRAP})

TOPICS = {
    "PO": "supplychain.purchase.orders",
    "SHIPMENT": "supplychain.shipment.updates",
    "QUALITY": "supplychain.quality.results",
    "DISRUPTION": "supplychain.disruption.alerts",
    "INVENTORY": "supplychain.inventory.levels",
}
REFERENCE_TOPICS = {
    "SUPPLIERS": "supplychain.master.suppliers",
    "PARTS": "supplychain.master.parts",
    "FACILITIES": "supplychain.master.facilities",
}

SUPPLIERS = [f"supplier-{i:04d}" for i in range(1, SUPPLIER_POOL + 1)]
FACILITIES = [f"facility-{i:03d}" for i in range(1, FACILITY_POOL + 1)]
PARTS = [f"part-{i:05d}" for i in range(1, PART_POOL + 1)]

FACILITY_TYPES = ["factory", "warehouse", "distribution_center", "port", "cross_dock", "cold_storage"]
REGIONS = ["NA-East", "NA-West", "EU-West", "EU-East", "APAC-China", "APAC-SEA", "APAC-India", "LATAM", "MEA"]
COUNTRIES = ["US", "CN", "DE", "JP", "KR", "MX", "IN", "VN", "TW", "TH", "MY", "BR", "GB", "FR", "IT"]
HIGH_RISK_REGIONS = {"CN", "RU", "TW", "VN", "MM"}
COMMODITIES = ["Electronics", "Automotive", "Pharmaceuticals", "Chemicals", "Metals", "Plastics", "Textiles", "Aerospace"]
PART_NAMES = [
    "MCU-ARM-Cortex-M4", "MLCC-0402-100nF", "Power-MOSFET-N-Ch", "Li-Ion-Cell-18650",
    "Connector-USB-C", "PCB-4Layer-FR4", "Resistor-0603-10K", "LED-SMD-White",
    "DC-DC-Converter-5V", "Sensor-IMU-6Axis", "DRAM-DDR4-8Gb", "NAND-Flash-256Gb",
    "Inductor-SMD-10uH", "Crystal-32MHz", "Antenna-WiFi-2.4G", "Heat-Sink-Al-40mm",
    "Gasket-Silicone-ORing", "Bearing-608ZZ", "Steel-Sheet-1mm", "Aluminum-Extrusion-T6",
    "Rubber-Compound-EPDM", "Adhesive-Epoxy-2Part", "Glass-Gorilla-Gen6", "Fabric-Nylon-600D",
    "Resin-ABS-Natural", "Copper-Wire-AWG22", "Solder-Paste-SAC305", "Thermal-Pad-3W",
    "Spring-Compression-SS", "Screw-M3x8-SS304",
]
DISRUPTION_TYPES = [
    "port_closure", "factory_shutdown", "raw_material_shortage", "transport_delay",
    "quality_hold", "sanctions_compliance", "natural_disaster", "labor_strike",
    "equipment_failure", "cyber_incident",
]
SOURCE_SYSTEMS = ["SAP-ERP", "Oracle-SCM", "Manhattan-WMS", "BluJay-TMS", "IoT-Gateway", "Coupa-Procurement"]
SHIPMENT_STATUSES = ["booked", "in_transit", "at_port", "customs_hold", "delivered", "delayed", "lost"]
PO_STATUSES = ["created", "confirmed", "partially_shipped", "shipped", "received", "closed", "cancelled"]
QUALITY_RESULTS = ["pass", "conditional_pass", "fail", "hold_for_review"]
INCOTERMS = ["EXW", "FOB", "CIF", "DDP", "DAP", "FCA"]
TRANSPORT_MODES = ["ocean", "air", "rail", "truck", "multimodal"]

# Stateful tracking
SUPPLIER_PART_MAP: dict[str, list[str]] = {}
PO_STATE: dict[str, dict] = {}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _iso_shifted(minutes: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def event_envelope(source_system, source_type, event_type, entity_id, facility_id, supplier_id, payload):
    return {
        "event_id": str(uuid.uuid4()),
        "event_ts": now_iso(),
        "source_system": source_system,
        "source_type": source_type,
        "event_type": event_type,
        "entity_id": entity_id,
        "facility_id": facility_id,
        "supplier_id": supplier_id,
        "payload_json": json.dumps(payload),
        "schema_version": "1.0.0",
    }


def apply_temporal_noise(event, payload):
    if random.random() < LATE_EVENT_PROBABILITY:
        lag = random.randint(10, 240)
        event["event_ts"] = _iso_shifted(minutes=-lag)
        payload["late_arrival_minutes"] = lag
        event["payload_json"] = json.dumps(payload)
    return event, payload


def _supplier_parts(supplier_id):
    if supplier_id not in SUPPLIER_PART_MAP:
        count = random.randint(1, 8)
        SUPPLIER_PART_MAP[supplier_id] = random.sample(PARTS, min(count, len(PARTS)))
    return SUPPLIER_PART_MAP[supplier_id]


# ── Transactional event generators ────────────────────────────────────────────

def purchase_order_event():
    supplier = random.choice(SUPPLIERS)
    part = random.choice(_supplier_parts(supplier))
    facility = random.choice(FACILITIES)
    qty = random.randint(100, 50000)
    unit_price = round(random.uniform(0.01, 250.0), 4)
    payload = {
        "po_number": f"PO-{random.randint(100000, 999999)}",
        "supplier_id": supplier,
        "part_id": part,
        "part_name": random.choice(PART_NAMES),
        "quantity": qty,
        "unit_price": unit_price,
        "total_value": round(qty * unit_price, 2),
        "currency": random.choice(["USD", "EUR", "CNY", "JPY"]),
        "destination_facility": facility,
        "incoterm": random.choice(INCOTERMS),
        "expected_delivery_date": fake.date_between(start_date="+7d", end_date="+90d").isoformat(),
        "status": random.choice(PO_STATUSES),
        "commodity_category": random.choice(COMMODITIES),
    }
    event = event_envelope("SAP-ERP", "PROCUREMENT", "PURCHASE_ORDER", part, facility, supplier, payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["PO"], event


def shipment_update_event():
    supplier = random.choice(SUPPLIERS)
    part = random.choice(_supplier_parts(supplier))
    origin = random.choice(FACILITIES)
    destination = random.choice([f for f in FACILITIES if f != origin] or FACILITIES)
    expected_days = random.randint(3, 45)
    actual_days = expected_days + random.randint(-2, 15)
    payload = {
        "shipment_id": f"SHP-{random.randint(100000, 999999)}",
        "supplier_id": supplier,
        "part_id": part,
        "origin_facility": origin,
        "destination_facility": destination,
        "transport_mode": random.choice(TRANSPORT_MODES),
        "carrier": fake.company()[:30],
        "container_id": f"CONT-{random.randint(10000, 99999)}" if random.random() > 0.3 else None,
        "status": random.choice(SHIPMENT_STATUSES),
        "expected_lead_days": expected_days,
        "actual_lead_days": actual_days,
        "quantity": random.randint(100, 20000),
        "weight_kg": round(random.uniform(10, 25000), 1),
        "customs_cleared": random.choice([True, False]),
    }
    event = event_envelope("BluJay-TMS", "LOGISTICS", "SHIPMENT_UPDATE", part, destination, supplier, payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["SHIPMENT"], event


def quality_result_event():
    supplier = random.choice(SUPPLIERS)
    part = random.choice(_supplier_parts(supplier))
    facility = random.choice(FACILITIES)
    sample_size = random.randint(10, 500)
    defects = random.randint(0, int(sample_size * 0.15))
    defect_rate = round(defects / sample_size, 4) if sample_size else 0
    result = "pass" if defect_rate < 0.02 else ("conditional_pass" if defect_rate < 0.05 else "fail")
    payload = {
        "inspection_id": f"QI-{random.randint(100000, 999999)}",
        "supplier_id": supplier,
        "part_id": part,
        "facility_id": facility,
        "inspection_type": random.choice(["incoming", "in_process", "final", "audit"]),
        "sample_size": sample_size,
        "defects_found": defects,
        "defect_rate": defect_rate,
        "result": result,
        "defect_categories": random.sample(
            ["dimensional", "cosmetic", "functional", "material", "labeling", "contamination"],
            k=min(defects, 3) if defects > 0 else 0,
        ),
        "corrective_action_required": result == "fail",
    }
    event = event_envelope("Oracle-SCM", "QUALITY", "QUALITY_RESULT", part, facility, supplier, payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["QUALITY"], event


def disruption_alert_event():
    facility = random.choice(FACILITIES)
    disruption_type = random.choice(DISRUPTION_TYPES)
    severity = random.choice(["low", "moderate", "high", "critical"])
    affected_parts = random.sample(PARTS, k=random.randint(1, 5))
    payload = {
        "disruption_id": f"DIS-{random.randint(100000, 999999)}",
        "facility_id": facility,
        "disruption_type": disruption_type,
        "severity": severity,
        "region": random.choice(REGIONS),
        "country": random.choice(COUNTRIES),
        "affected_parts": affected_parts,
        "estimated_duration_days": random.randint(1, 90),
        "description": f"{disruption_type.replace('_', ' ').title()} at {facility}. Severity: {severity}.",
        "mitigation_status": random.choice(["not_started", "in_progress", "mitigated", "escalated"]),
    }
    event = event_envelope("IoT-Gateway", "RISK", "DISRUPTION_ALERT", None, facility, None, payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["DISRUPTION"], event


def inventory_level_event():
    facility = random.choice(FACILITIES)
    part = random.choice(PARTS)
    on_hand = random.randint(0, 50000)
    reorder_point = random.randint(500, 5000)
    payload = {
        "facility_id": facility,
        "part_id": part,
        "on_hand_qty": on_hand,
        "allocated_qty": random.randint(0, on_hand),
        "in_transit_qty": random.randint(0, 10000),
        "reorder_point": reorder_point,
        "below_reorder": on_hand < reorder_point,
        "days_of_supply": round(on_hand / max(random.randint(50, 500), 1), 1),
        "warehouse_zone": random.choice(["A", "B", "C", "BULK", "HAZMAT", "COLD"]),
    }
    event = event_envelope("Manhattan-WMS", "INVENTORY", "INVENTORY_LEVEL", part, facility, None, payload)
    return TOPICS["INVENTORY"], event


# ── Reference event generators ────────────────────────────────────────────────

def supplier_reference_event():
    supplier = random.choice(SUPPLIERS)
    country = random.choice(COUNTRIES)
    payload = {
        "supplier_id": supplier,
        "name": fake.company(),
        "country": country,
        "region": random.choice(REGIONS),
        "commodity_categories": random.sample(COMMODITIES, k=random.randint(1, 3)),
        "tier": random.choice(["tier_1", "tier_2", "tier_3"]),
        "risk_score": round(random.uniform(0, 100), 1),
        "iso_certified": random.choice([True, False]),
        "geopolitical_risk": country in HIGH_RISK_REGIONS,
    }
    return REFERENCE_TOPICS["SUPPLIERS"], event_envelope("Coupa-Procurement", "REFERENCE", "SUPPLIER_MASTER_UPSERT", None, None, supplier, payload)


def part_reference_event():
    part = random.choice(PARTS)
    payload = {
        "part_id": part,
        "part_name": random.choice(PART_NAMES),
        "commodity_category": random.choice(COMMODITIES),
        "criticality": random.choice(["low", "medium", "high", "critical"]),
        "unit_of_measure": random.choice(["EA", "KG", "M", "L", "BOX"]),
        "lead_time_days": random.randint(3, 120),
        "supplier_count": random.randint(1, 6),
        "single_source": random.random() < 0.25,
    }
    return REFERENCE_TOPICS["PARTS"], event_envelope("SAP-ERP", "REFERENCE", "PART_MASTER_UPSERT", part, None, None, payload)


def facility_reference_event():
    facility = random.choice(FACILITIES)
    payload = {
        "facility_id": facility,
        "name": f"{fake.city()} {random.choice(['Plant', 'DC', 'Warehouse', 'Hub'])}",
        "facility_type": random.choice(FACILITY_TYPES),
        "country": random.choice(COUNTRIES),
        "region": random.choice(REGIONS),
        "capacity_utilization": round(random.uniform(0.3, 1.0), 2),
        "operational_status": random.choice(["operational", "maintenance", "limited", "shutdown"]),
    }
    return REFERENCE_TOPICS["FACILITIES"], event_envelope("Oracle-SCM", "REFERENCE", "FACILITY_MASTER_UPSERT", None, facility, None, payload)


GENERATORS = [purchase_order_event, shipment_update_event, quality_result_event, disruption_alert_event, inventory_level_event]
REFERENCE_GENERATORS = [supplier_reference_event, part_reference_event, facility_reference_event]


# ── Infrastructure ────────────────────────────────────────────────────────────

def wait_for_schema_registry():
    deadline = time.time() + SCHEMA_REGISTRY_STARTUP_TIMEOUT
    while time.time() < deadline:
        try:
            r = requests.get(f"{SCHEMA_REGISTRY_URL}/subjects", timeout=5)
            if r.status_code == 200:
                print("Schema Registry is ready.")
                return
        except Exception as ex:
            print(f"Waiting for Schema Registry: {ex}")
        time.sleep(SCHEMA_REGISTRY_RETRY_INTERVAL)
    raise RuntimeError("Schema Registry did not become ready")


def register_schema():
    with open("schemas/supply_chain_event.avsc", "r", encoding="utf-8") as f:
        schema = f.read()
    for topic in list(TOPICS.values()) + list(REFERENCE_TOPICS.values()):
        subject = f"{topic}-value"
        url = f"{SCHEMA_REGISTRY_URL}/subjects/{subject}/versions"
        payload = {"schemaType": "AVRO", "schema": schema}
        deadline = time.time() + SCHEMA_REGISTRY_STARTUP_TIMEOUT
        while time.time() < deadline:
            try:
                r = requests.post(url, json=payload, timeout=10)
                if r.status_code in {200, 201, 409}:
                    print(f"Schema registered: {subject} status={r.status_code}")
                    break
            except Exception as ex:
                print(f"Schema retry {subject}: {ex}")
            time.sleep(SCHEMA_REGISTRY_RETRY_INTERVAL)


def build_avro_serializer():
    with open("schemas/supply_chain_event.avsc", "r", encoding="utf-8") as f:
        schema = f.read()
    sr_client = SchemaRegistryClient({"url": SCHEMA_REGISTRY_URL})
    return AvroSerializer(schema_registry_client=sr_client, schema_str=schema, to_dict=lambda obj, ctx: obj)


def _on_delivery(err, msg):
    if err is not None:
        print(f"Delivery failed for {msg.topic() if msg else '?'}: {err}")


wait_for_schema_registry()
register_schema()
avro_serializer = build_avro_serializer()


def _emit(topic, event):
    key = event.get("entity_id") or event.get("facility_id") or event["event_id"]
    val = avro_serializer(event, SerializationContext(topic, MessageField.VALUE))
    producer.produce(topic, key=key.encode("utf-8"), value=val, on_delivery=_on_delivery)
    print(f"Produced {event['event_type']} to {topic}: {event['event_id']}")


while True:
    for _ in range(TX_EVENTS_PER_INTERVAL):
        topic, event = random.choice(GENERATORS)()
        _emit(topic, event)
    for _ in range(REF_EVENTS_PER_INTERVAL):
        topic, event = random.choice(REFERENCE_GENERATORS)()
        _emit(topic, event)
    producer.flush()
    time.sleep(INTERVAL)
