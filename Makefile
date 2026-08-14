# Makefile for local development operations.
# Usage: make <target>

INFRA   := docker-compose.infra.yml
HC      := docker-compose.healthcare.yml
SC      := docker-compose.supply-chain.yml
NET     := graphrag-net
DC_INFRA := docker compose -f $(INFRA) -p infra
DC_HC    := docker compose -f $(HC) -p healthcare
DC_SC    := docker compose -f $(SC) -p supplychain

.PHONY: help up up-hc up-sc up-all down down-all build build-hc build-sc \
        ps logs restart clean neo4j-hc neo4j-sc qdrant-hc qdrant-sc \
        validate test-hc query-hc query-sc pull-model shell-kafka topics

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Stack lifecycle ───────────────────────────────────────────────────────────

up: ## Start infra + healthcare + supply-chain as separate groups
	docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d
	$(DC_HC) up -d
	$(DC_SC) up -d

up-hc: ## Start infra + healthcare domain
	docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d
	$(DC_HC) up -d

up-sc: ## Start infra + supply-chain domain
	docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d
	$(DC_SC) up -d

up-all: up ## Alias for up

down: ## Stop healthcare + infra
	$(DC_HC) down
	$(DC_INFRA) down

down-all: ## Stop all domains + infra
	$(DC_SC) down --remove-orphans
	$(DC_HC) down --remove-orphans
	$(DC_INFRA) down --remove-orphans
	docker network rm $(NET) 2>/dev/null || true

build: build-hc ## Build healthcare images (default)

build-hc: ## Build healthcare domain images
	$(DC_HC) build

build-sc: ## Build supply-chain domain images
	$(DC_SC) build

build-all: ## Build all domain images
	$(DC_HC) build
	$(DC_SC) build

restart: ## Restart healthcare domain services
	$(DC_HC) down && $(DC_HC) up -d

clean: ## Stop all, remove volumes, prune
	$(DC_SC) down -v --remove-orphans 2>/dev/null || true
	$(DC_HC) down -v --remove-orphans 2>/dev/null || true
	$(DC_INFRA) down -v --remove-orphans 2>/dev/null || true
	docker network rm $(NET) 2>/dev/null || true
	docker system prune -f

# ── Status and logs ───────────────────────────────────────────────────────────

ps: ## Show all running containers
	docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | sort

logs: ## Tail logs for healthcare services
	$(DC_HC) logs -f --tail 20

logs-sc: ## Tail logs for supply-chain services
	$(DC_SC) logs -f --tail 20 sc-producer sc-flink-processor sc-rag-api

# ── Neo4j access ─────────────────────────────────────────────────────────────

neo4j-hc: ## Open healthcare Neo4j cypher-shell
	docker exec -it healthcare-neo4j cypher-shell -u neo4j -p healthcare123

neo4j-sc: ## Open supply-chain Neo4j cypher-shell
	docker exec -it supplychain-neo4j cypher-shell -u neo4j -p supplychain123

# ── Qdrant access ────────────────────────────────────────────────────────────

qdrant-hc: ## Show healthcare Qdrant collection info
	@curl -s http://localhost:6333/collections/healthcare_events | python3 -m json.tool

qdrant-sc: ## Show supply-chain Qdrant collection info
	@curl -s http://localhost:6335/collections/supplychain_events | python3 -m json.tool

# ── RAG API ───────────────────────────────────────────────────────────────────

query-hc: ## Run healthcare query examples
	./domains/healthcare/scripts/query_examples.sh

query-sc: ## Run supply-chain query examples
	./domains/supply-chain/scripts/query_examples.sh

api-hc: ## Check healthcare RAG API health
	@curl -s http://localhost:8000/health | python3 -m json.tool

api-sc: ## Check supply-chain RAG API health
	@curl -s http://localhost:8001/health | python3 -m json.tool

# ── Kafka ─────────────────────────────────────────────────────────────────────

topics: ## List all Kafka topics
	docker exec infra-kafka kafka-topics --bootstrap-server kafka:29092 --list

shell-kafka: ## Open shell in Kafka broker
	docker exec -it infra-kafka bash

# ── Validation ────────────────────────────────────────────────────────────────

validate: ## Run cross-domain stack validation
	./scripts/validate_stack.sh

validate-docs: ## Run markdown lint
	./scripts/validate_docs.sh

test-hc: ## Run healthcare domain tests
	cd domains/healthcare && python3 scripts/validate_ontology.py && python3 scripts/test_neo4j_bootstrap.py && python3 scripts/validate_terminology_coverage.py

test-sc: ## Run supply-chain domain tests
	cd domains/supply-chain && python3 scripts/validate_ontology.py && python3 scripts/test_neo4j_bootstrap.py

# ── Model ─────────────────────────────────────────────────────────────────────

pull-model: ## Pull Ollama LLM model
	docker exec infra-ollama ollama pull llama3.1

# ── Shortcuts ─────────────────────────────────────────────────────────────────

fresh: clean up-all pull-model ## Full fresh start with both domains
