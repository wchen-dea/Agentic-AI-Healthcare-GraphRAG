# Usage: make <target>

INFRA    := infra/compose/docker-compose.infra.yml
HC       := infra/compose/docker-compose.healthcare.yml
SC       := infra/compose/docker-compose.supply-chain.yml
NET      := graphrag-net
DC_INFRA := docker compose -f $(INFRA) -p infra
DC_HC    := docker compose -f $(HC) -p healthcare
DC_SC    := docker compose -f $(SC) -p supplychain

.PHONY: help up up-hc up-sc down compose-up compose-up-hc compose-up-sc compose-down \
	        minikube-up minikube-down minikube-ports minikube-ports-stop \
	        build build-hc build-sc build-all restart restart-sc clean ps logs logs-sc \
	        neo4j-hc neo4j-sc qdrant-hc qdrant-sc query-hc query-sc api-hc api-sc \
	        flink-hc flink-sc mlflow topics shell-kafka validate validate-docs \
	        validate-skills generate-skills validate-ontology sync test-core test-hc \
	        test-sc test-unit test-integration test-evals lint build-wheels \
	        web-hc-dev web-hc-test web-hc-build pull-model fresh \
	        helm-dev helm-dev-down helm-ports helm-ports-stop helm-prd helm-lint

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Local path 1: Docker Compose

compose-up: ## Start the full stack with Docker Compose only
	@docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d && $(DC_HC) up -d && $(DC_SC) up -d

compose-up-hc: ## Start Compose infrastructure and healthcare
	@docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d && $(DC_HC) up -d

compose-up-sc: ## Start Compose infrastructure and supply chain
	@docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d && $(DC_SC) up -d

compose-down: ## Stop Docker Compose and remove its network
	$(DC_SC) down --remove-orphans; $(DC_HC) down --remove-orphans; $(DC_INFRA) down --remove-orphans
	docker network rm $(NET) 2>/dev/null || true

up: compose-up ## Backward-compatible Compose alias
up-hc: compose-up-hc ## Backward-compatible Compose alias
up-sc: compose-up-sc ## Backward-compatible Compose alias
down: compose-down ## Backward-compatible Compose alias

build: build-hc ## Build healthcare images
build-hc:
	$(DC_HC) build
build-sc:
	$(DC_SC) build
build-all: build-hc build-sc ## Build all domain images

restart: ## Restart healthcare services
	$(DC_HC) down && $(DC_HC) up -d
restart-sc: ## Restart supply-chain services
	$(DC_SC) down && $(DC_SC) up -d

clean: ## Stop all, remove volumes, and prune Docker
	$(DC_SC) down -v --remove-orphans 2>/dev/null || true
	$(DC_HC) down -v --remove-orphans 2>/dev/null || true
	$(DC_INFRA) down -v --remove-orphans 2>/dev/null || true
	docker network rm $(NET) 2>/dev/null || true
	docker system prune -f

# Observation and service access

ps: ## Show running containers
	@docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | sort
logs: ## Tail healthcare logs
	$(DC_HC) logs -f --tail 20
logs-sc: ## Tail supply-chain logs
	$(DC_SC) logs -f --tail 20 sc-producer sc-flink-app sc-agent-service

neo4j-hc: ## Open healthcare Neo4j shell
	docker exec -it healthcare-neo4j cypher-shell -u neo4j -p healthcare123
neo4j-sc: ## Open supply-chain Neo4j shell
	docker exec -it supplychain-neo4j cypher-shell -u neo4j -p supplychain123
qdrant-hc: ## Show healthcare Qdrant collection
	@curl -s http://localhost:6333/collections/healthcare_events | python3 -m json.tool
qdrant-sc: ## Show supply-chain Qdrant collection
	@curl -s http://localhost:6335/collections/supplychain_events | python3 -m json.tool
api-hc: ## Check healthcare agent health
	@curl -s http://localhost:8000/health | python3 -m json.tool
api-sc: ## Check supply-chain agent health
	@curl -s http://localhost:8001/health | python3 -m json.tool
query-hc: ## Run healthcare query examples
	./domains/healthcare/scripts/query_examples.sh
query-sc: ## Run supply-chain query examples
	./domains/supply-chain/scripts/query_examples.sh
flink-hc: ## Show healthcare Flink jobs
	@curl -s http://localhost:8082/jobs/overview | python3 -m json.tool
flink-sc: ## Show supply-chain Flink jobs
	@curl -s http://localhost:8083/jobs/overview | python3 -m json.tool
mlflow: ## Check MLflow health
	@curl -s http://localhost:5000/health && echo
topics: ## List Kafka topics
	docker exec infra-kafka kafka-topics --bootstrap-server kafka:29092 --list
shell-kafka: ## Open Kafka shell
	docker exec -it infra-kafka bash

# Validation and tests

HC_WEB := domains/healthcare/webapp
web-hc-dev: ## Start healthcare web UI development server
	cd $(HC_WEB) && npm install && VITE_API_BASE_URL=/api npm run dev
web-hc-test: ## Run healthcare web UI tests
	cd $(HC_WEB) && npm ci && npm run typecheck && npm test
web-hc-build: ## Build healthcare web UI
	cd $(HC_WEB) && npm ci && npm run build
validate: ## Validate all stacks
	./scripts/validate_all_stacks.sh
validate-docs: ## Validate Markdown
	./scripts/validate_docs.sh
validate-skills: ## Validate generated skills
	python domains/healthcare/scripts/generate_agent_skills.py --check
	python domains/healthcare/scripts/validate_agent_skills.py
	python domains/supply-chain/scripts/generate_agent_skills.py --check
	python domains/supply-chain/scripts/validate_agent_skills.py
generate-skills: ## Generate skills
	python domains/healthcare/scripts/generate_agent_skills.py
	python domains/supply-chain/scripts/generate_agent_skills.py
validate-ontology: ## Validate ontologies
	python domains/healthcare/scripts/validate_ontology.py
	python domains/supply-chain/scripts/validate_ontology.py
sync: ## Sync the uv workspace
	uv sync
test-core: ## Run agent-core tests
	cd packages/agent-core && uv run --package agent-core pytest --tb=short
test-hc: ## Run healthcare tests
	cd domains/healthcare/agent-service && uv run --package healthcare-agent-service pytest --tb=short
test-sc: ## Run supply-chain tests
	cd domains/supply-chain/agent-service && uv run --package supply-chain-agent-service pytest --tb=short
lint: ## Run Ruff
	uv run ruff check packages domains scripts
test-unit: ## Run unit tests
	cd packages/agent-core && uv run --package agent-core pytest --tb=short tests/unit
	cd domains/healthcare/agent-service && uv run --package healthcare-agent-service pytest --tb=short tests/unit
	cd domains/supply-chain/agent-service && uv run --package supply-chain-agent-service pytest --tb=short tests/unit
test-integration: ## Run integration tests
	cd domains/healthcare/agent-service && uv run --package healthcare-agent-service pytest --tb=short tests/integration
	cd domains/supply-chain/agent-service && uv run --package supply-chain-agent-service pytest --tb=short tests/integration
test-evals: ## Run evaluation tests
	cd domains/healthcare/agent-service && uv run --package healthcare-agent-service pytest --tb=short tests/evals
build-wheels: ## Build workspace wheels
	uv build --wheel --package agent-core --out-dir dist
	uv build --wheel --package knowledge-core --out-dir dist
	uv build --wheel --package healthcare-agent-service --out-dir dist
	uv build --wheel --package supply-chain-agent-service --out-dir dist
pull-model: ## Pull the Ollama model
	docker exec infra-ollama ollama pull llama3.1
fresh: clean compose-up ## Full fresh Compose start

# Local path 2: Minikube with the Docker driver

minikube-up: ## Start Minikube with Docker driver and deploy Helm
	MINIKUBE_DRIVER=docker infra/environments/dev/setup-minikube.sh
minikube-down: ## Remove the Minikube Helm release
	helm uninstall healthcare-dev -n healthcare-ai-dev || true
minikube-ports: ## Start Minikube port-forwards
	$(MAKE) helm-ports
minikube-ports-stop: ## Stop Minikube port-forwards
	$(MAKE) helm-ports-stop

helm-dev: minikube-up ## Backward-compatible Minikube alias
helm-dev-down: minikube-down ## Backward-compatible Minikube teardown
helm-ports: ## Start Minikube port-forwards
	@pkill -f "port-forward" 2>/dev/null || true
	@kubectl -n healthcare-ai-dev port-forward svc/agent-service 8000:8000 >/dev/null 2>&1 &
	@kubectl -n healthcare-ai-dev port-forward svc/provider-web 8088:80 >/dev/null 2>&1 &
	@kubectl -n healthcare-ai-dev port-forward svc/neo4j 7474:7474 7687:7687 >/dev/null 2>&1 &
	@kubectl -n healthcare-ai-dev port-forward svc/qdrant 6333:6333 >/dev/null 2>&1 &
	@kubectl -n healthcare-ai-dev port-forward svc/conduktor-console 9080:8080 >/dev/null 2>&1 &
	@sleep 2
	@echo "Agent API: http://localhost:8000"
	@echo "Web UI: http://localhost:8088"
	@echo "Neo4j: http://localhost:7474"
	@echo "Qdrant: http://localhost:6333/dashboard"
	@echo "Conduktor: http://localhost:9080"
helm-ports-stop: ## Stop Minikube port-forwards
	@pkill -f "port-forward" 2>/dev/null || true
	@echo "Port-forwards stopped."
helm-prd: ## Render production Helm manifests
	helm template healthcare infra/helm -f infra/helm/values-production.yaml
helm-lint: ## Lint and render Helm environments
	helm lint infra/helm
	helm template dev infra/helm -f infra/helm/values-dev.yaml >/dev/null
	helm template prd infra/helm -f infra/helm/values-production.yaml >/dev/null
	@echo "Helm lint: OK"
