# Supply Chain Resilience Domain

Parallel domain implementation running alongside the Healthcare Provider domain.

## What It Does

Ingests synthetic supply chain events (purchase orders, shipments, quality inspections, disruption alerts, inventory levels) through the shared Kafka cluster, processes them into a dedicated Neo4j graph and Qdrant vector store, and enables GraphRAG queries for supplier risk, logistics tracking, quality analysis, and disruption impact assessment.

## Architecture

Shares infrastructure with the healthcare stack:

| Shared | Domain-Isolated |
|--------|----------------|
| Kafka cluster (3 brokers) | Neo4j instance (port 7475/7688) |
| Schema Registry | Qdrant collection (port 6335) |
| Prometheus + Grafana | Kafka topics (`supplychain.*`) |
| Ollama LLM | Producer, graph writes, ontology seeds |

## Graph Model

| Node | Key | Description |
|------|-----|-------------|
| Supplier | id | Organization providing parts/materials |
| Part | id | Component, material, or finished good |
| Facility | id | Factory, warehouse, DC, or port |
| Shipment | id | Tracked goods movement |
| PurchaseOrder | id | Contractual order |
| QualityInspection | id | Inbound/in-process quality check |
| DisruptionEvent | id | Supply chain disruption |
| RiskSignal | id | Computed risk indicator |

Key relationships: `SUPPLIES`, `DEPENDS_ON` (BOM), `SHIPPED_FROM/TO`, `DISRUPTED_BY`, `AFFECTS_PART`, `HAS_RISK_SIGNAL`, `HOLDS_INVENTORY`.

## Event Types

| Topic | Event Type | Generator |
|-------|-----------|-----------|
| supplychain.purchase.orders | PURCHASE_ORDER | purchase_order_event |
| supplychain.shipment.updates | SHIPMENT_UPDATE | shipment_update_event |
| supplychain.quality.results | QUALITY_RESULT | quality_result_event |
| supplychain.disruption.alerts | DISRUPTION_ALERT | disruption_alert_event |
| supplychain.inventory.levels | INVENTORY_LEVEL | inventory_level_event |
| supplychain.master.suppliers | SUPPLIER_MASTER_UPSERT | supplier_reference_event |
| supplychain.master.parts | PART_MASTER_UPSERT | part_reference_event |
| supplychain.master.facilities | FACILITY_MASTER_UPSERT | facility_reference_event |

## Quick Start

From the repository root:

```bash
docker compose -f docker-compose.infra.yml -f docker-compose.healthcare.yml \
  -f domains/supply-chain/docker-compose.supply-chain.yml \
  up -d --build
```

Verify Neo4j:

```bash
docker compose exec supplychain-neo4j cypher-shell \
  -u neo4j -p supplychain123 \
  "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC;"
```

## Directory Structure

```
domains/supply-chain/
├── config/ontology/          # Entity definitions, seeds, risk signal rules
├── flink-app/app/            # graph_writes.py, pipeline_service.py
├── neo4j/                    # init.cypher, seeds, bootstrap.sh
├── producer/                 # Dockerfile, produce_events.py, requirements.txt
├── rag-api/                  # app.py, skills_layer.py, domain/, config/
├── schemas/                  # supply_chain_event.avsc
├── scripts/                  # query_examples.sh, validate_ontology.py, etc.
├── skills/                   # Agent Skills packages (SKILL.md)
└── webapp/                   # index.html, domain.js, Dockerfile
```

Note: `docker-compose.supply-chain.yml` lives at the repository root.

## RAG Query Request Types

| Type | Trigger Keywords |
|------|-----------------|
| supplier_risk | risk, single source, geopolitical, exposure |
| shipment_tracking | shipment, transit, delivery, delayed, customs |
| quality_review | quality, defect, inspection, rejection |
| disruption_impact | disruption, shutdown, closure, strike, disaster |
| inventory_planning | inventory, stock, reorder, days of supply |
| procurement_overview | (default) |

## Default Credentials

```
Neo4j: neo4j / supplychain123
Bolt:  bolt://localhost:7688
HTTP:  http://localhost:7475
```
