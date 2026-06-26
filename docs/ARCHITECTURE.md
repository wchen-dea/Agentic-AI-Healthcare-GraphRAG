# Healthcare Hybrid GraphRAG Architecture

## Purpose

This project demonstrates a local healthcare event platform that combines streaming ingestion, vector retrieval, graph reasoning, and local LLM generation in one reproducible Docker Compose environment.

The architecture is designed to show how transactional clinical events and slower-changing master data can be combined into a GraphRAG workflow.

## Runtime Topology

```text
Synthetic producers
  -> Kafka domain topics
  -> Schema Registry
  -> Streaming processor in flink-app container
     -> in-memory reference store for master data
     -> Qdrant vector sink
     -> Neo4j graph sink
  -> FastAPI RAG API
     -> Qdrant semantic retrieval
     -> Neo4j patient relationship retrieval
     -> Ollama answer generation

Operations plane
  -> Conduktor for Kafka administration
  -> Prometheus + Blackbox Exporter for metrics and probes
  -> Grafana dashboards and alerts
  -> Neo4j Browser + NeoDash for graph inspection
  -> Provider web app for human query workflow
```

## Main Components

### Producer

The producer emits two categories of events:

- transactional healthcare events such as clinical notes, lab results, telemetry, medication orders, and claims,
- master-data reference events for patients, providers, devices, medications, and payers.

The producer registers the Avro envelope schema in Schema Registry, but publishes JSON payloads for simplicity.

### Kafka And Schema Registry

Kafka is the event backbone. Topics are created explicitly on startup by the `kafka-init` service. Schema Registry stores the shared `MedicalEvent` envelope contract for all topics.

### Streaming Processor

The core stream logic lives in `flink-app/healthcare_graph_rag_job.py`.

Important implementation detail:

- this is not a native PyFlink DataStream job,
- it is a Python process running inside a Flink-oriented container,
- it consumes Kafka topics directly via `confluent_kafka.Consumer`.

The processor:

1. subscribes to both transactional and reference topics,
2. updates an in-memory reference store from master-data events,
3. enriches transactional events with matching reference context,
4. generates deterministic embeddings from rendered clinical text,
5. writes vector records to Qdrant,
6. writes structured graph state to Neo4j.

### Qdrant

Qdrant stores the semantic representation of processed events in the `healthcare_events` collection. Stored payload includes:

- event identifiers,
- patient and source metadata,
- enrichment flags,
- rendered clinical text,
- original event payload.

### Neo4j

Neo4j stores the patient-centric relationship graph. It contains both event-derived clinical entities and reference-derived entities such as provider, device, medication metadata, and payer coverage.

### RAG API

The FastAPI service in `rag-api/app.py` provides the `/query` endpoint.

Request flow:

1. embed the incoming question using the same deterministic embedding approach used for event text,
2. search Qdrant for nearest event evidence,
3. derive patient IDs from vector results and optional request filter,
4. query Neo4j for graph context around those patients,
5. construct a combined prompt,
6. call Ollama for a final synthesized answer.

### Ollama

Ollama provides local generation. The API defaults to `llama3.1` and can resolve an available local variant such as `llama3.1:latest` when needed.

### Provider Web App

The provider web app is a static browser client that calls the RAG API directly and renders answer, vector context, and graph context for interactive local testing.

### Operational Tooling

- Conduktor for Kafka browsing and cluster visibility
- Prometheus for scraping and rule evaluation
- Blackbox Exporter for Neo4j, Kafka, and Flink probes
- Grafana for dashboards
- Neo4j Browser and NeoDash for graph exploration

## Event Flow

### Transactional Flow

```text
Producer
  -> healthcare.* transactional topic
  -> streaming processor
  -> enriched clinical text
  -> Qdrant upsert
  -> Neo4j merge operations
  -> queryable by API
```

### Reference-Data Flow

```text
Producer
  -> healthcare.master.* topic
  -> streaming processor
  -> in-memory reference store update
  -> later transactional event enrichment
```

Reference data is not queried directly through the API. Instead, it improves the quality of:

- vector text rendering,
- graph node properties and relationships,
- downstream prompt context.

## Topic Categories

| Category | Topics | Purpose |
| --- | --- | --- |
| Transactional | `healthcare.ehr.events`, `healthcare.lab.results`, `healthcare.device.telemetry`, `healthcare.pharmacy.orders`, `healthcare.claims.events` | Primary event ingestion |
| Reference | `healthcare.master.patients`, `healthcare.master.providers`, `healthcare.master.devices`, `healthcare.master.medications`, `healthcare.master.payers` | Enrichment data |
| Reserved | `healthcare.dlq.events` | Future dead-letter handling |

## Storage Responsibilities

| Layer | Stores | Retrieval Role |
| --- | --- | --- |
| Kafka | raw event stream | transport, replay, decoupling |
| Qdrant | semantic event vectors + payloads | nearest-neighbor evidence recall |
| Neo4j | explicit patient/event/reference relationships | relationship-aware context and reasoning |

## Observability Design

Prometheus configuration covers:

- direct scrape of Qdrant metrics,
- blackbox HTTP probe for Neo4j,
- blackbox TCP probe for Kafka,
- blackbox HTTP probe for Flink JobManager.

Alert rules currently cover:

- Neo4j availability and latency,
- Qdrant availability,
- Kafka availability,
- Flink JobManager availability.

## Known MVP Boundaries

- The producer registers Avro schemas but publishes JSON rather than Avro-encoded payloads.
- The stream processor uses an in-memory reference store, so reference state is not externally checkpointed.
- The embedding strategy is deterministic and lightweight rather than model-based.
- The DLQ topic exists but is not yet used by the processor.
- Native Flink APIs are not yet used for the processing loop.

## Recommended Next Hardening Steps

- move to native Flink Kafka source and managed state,
- serialize events with Avro or Protobuf on the wire,
- implement DLQ publishing and replay workflows,
- add authentication and tighter CORS policy to the API and provider UI,
- externalize credentials and operational defaults for production deployment.
