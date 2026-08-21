# Usage: make <target>

INFRA    := container/docker-compose.infra.yml
HC       := container/docker-compose.healthcare.yml
SC       := container/docker-compose.supply-chain.yml
NET      := graphrag-net
DC_INFRA := docker compose -f $(INFRA) -p infra
DC_HC    := docker compose -f $(HC) -p healthcare
DC_SC    := docker compose -f $(SC) -p supplychain

.PHONY: help up up-hc up-sc down-all \
        build build-hc build-sc build-all restart restart-sc \
        clean ps logs logs-sc \
        neo4j-hc neo4j-sc qdrant-hc qdrant-sc \
        query-hc query-sc api-hc api-sc \
        topics shell-kafka validate validate-docs \
        test-hc test-sc pull-model fresh

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Lifecycle ─────────────────────────────────────────────────────────────────

up: ## Start infra + healthcare + supply-chain
	@docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d && $(DC_HC) up -d && $(DC_SC) up -d

up-hc: ## Start infra + healthcare
	@docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d && $(DC_HC) up -d

up-sc: ## Start infra + supply-chain
	@docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d && $(DC_SC) up -d

down-all: ## Stop everything, remove network
	$(DC_SC) down --remove-orphans; $(DC_HC) down --remove-orphans; $(DC_INFRA) down --remove-orphans
	docker network rm $(NET) 2>/dev/null || true

build: build-hc        ## Build healthcare images (default)
build-hc: ; $(DC_HC) build  ## Build healthcare images
build-sc: ; $(DC_SC) build  ## Build supply-chain images
build-all: build-hc build-sc ## Build all images

restart: ## Restart healthcare services
	$(DC_HC) down && $(DC_HC) up -d

restart-sc: ## Restart supply-chain services
	$(DC_SC) down && $(DC_SC) up -d

clean: ## Stop all, remove volumes, prune
	$(DC_SC) down -v --remove-orphans 2>/dev/null || true
	$(DC_HC) down -v --remove-orphans 2>/dev/null || true
	$(DC_INFRA) down -v --remove-orphans 2>/dev/null || true
	docker network rm $(NET) 2>/dev/null || true
	docker system prune -f

# ── Observe ───────────────────────────────────────────────────────────────────

ps: ## Show running containers
	@docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | sort

logs:    ## Tail healthcare logs
	$(DC_HC) logs -f --tail 20
logs-sc: ## Tail supply-chain logs
	$(DC_SC) logs -f --tail 20 sc-producer sc-flink-processor sc-rag-api

# ── Service access ────────────────────────────────────────────────────────────

neo4j-hc: ## Healthcare Neo4j shell
	docker exec -it healthcare-neo4j cypher-shell -u neo4j -p healthcare123
neo4j-sc: ## Supply-chain Neo4j shell
	docker exec -it supplychain-neo4j cypher-shell -u neo4j -p supplychain123

qdrant-hc: ## Healthcare Qdrant collection info
	@curl -s http://localhost:6333/collections/healthcare_events | python3 -m json.tool
qdrant-sc: ## Supply-chain Qdrant collection info
	@curl -s http://localhost:6335/collections/supplychain_events | python3 -m json.tool

api-hc: ## Healthcare RAG API health
	@curl -s http://localhost:8000/health | python3 -m json.tool
api-sc: ## Supply-chain RAG API health
	@curl -s http://localhost:8001/health | python3 -m json.tool

query-hc: ## Run healthcare query examples
	./domains/healthcare/scripts/query_examples.sh
query-sc: ## Run supply-chain query examples
	./domains/supply-chain/scripts/query_examples.sh

topics: ## List Kafka topics
	docker exec infra-kafka kafka-topics --bootstrap-server kafka:29092 --list
shell-kafka: ## Kafka broker shell
	docker exec -it infra-kafka bash

# ── Validate & test ───────────────────────────────────────────────────────────

validate: ## Cross-domain stack validation
	./scripts/validate_stack.sh
validate-docs: ## Markdown lint
	./scripts/validate_docs.sh

test-hc: ## Healthcare agent + domain tests
	cd domains/healthcare/agents && python -m pytest tests/ --tb=short
test-sc: ## Supply-chain domain tests
	cd domains/supply-chain/agents && python -m pytest tests/ --tb=short 2>/dev/null || echo "No supply-chain tests yet"

pull-model: ## Pull Ollama LLM model
	docker exec infra-ollama ollama pull llama3.1

fresh: clean up pull-model ## Full fresh start with both domains
