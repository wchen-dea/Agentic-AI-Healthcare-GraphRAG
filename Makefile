# Usage: make <target>

.DEFAULT_GOAL := help

# Compose configuration
INFRA := infra/compose/docker-compose.infra.yml
HC := infra/compose/docker-compose.healthcare.yml
SC := infra/compose/docker-compose.supply-chain.yml
NET := graphrag-net

DC_INFRA := docker compose -f $(INFRA) -p infra
DC_HC := docker compose -f $(HC) -p healthcare
DC_SC := docker compose -f $(SC) -p supplychain

# Kubernetes configuration
KUBE_NAMESPACE := healthcare-ai-dev
KUBE_RELEASE := healthcare-dev
KUBE_CHART := infra/helm
KUBE_VALUES_DEV := infra/helm/values-dev.yaml
KUBE_VALUES_PRD := infra/helm/values-production.yaml
KUBE_SETUP := infra/environments/dev/setup-minikube.sh

HC_WEB := domains/healthcare/webapp

.PHONY: help \
	compose-up compose-up-hc compose-up-sc compose-down up up-hc up-sc down \
	build build-hc build-sc build-all restart restart-sc clean fresh pull-model \
	ps logs logs-sc neo4j-hc neo4j-sc qdrant-hc qdrant-sc api-hc api-sc \
	query-hc query-sc flink-hc flink-sc mlflow topics shell-kafka \
	web-hc-dev web-hc-test web-hc-build \
	validate validate-docs validate-skills generate-skills validate-ontology \
	sync lint test-core test-hc test-sc test-unit test-integration test-evals \
	build-wheels \
	minikube-up minikube-down minikube-ports minikube-ports-stop \
	helm-dev helm-dev-down helm-ports helm-ports-stop helm-lint helm-prd \
	kube-status kube-pods kube-logs

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_.-]+:.*## .*$$' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Docker Compose: local development
# ---------------------------------------------------------------------------

compose-up: ## Start infrastructure and both domain stacks
	@docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d && $(DC_HC) up -d && $(DC_SC) up -d

compose-up-hc: ## Start infrastructure and healthcare
	@docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d && $(DC_HC) up -d

compose-up-sc: ## Start infrastructure and supply chain
	@docker network create $(NET) 2>/dev/null || true
	$(DC_INFRA) up -d && $(DC_SC) up -d

compose-down: ## Stop Compose stacks and remove the shared network
	$(DC_SC) down --remove-orphans
	$(DC_HC) down --remove-orphans
	$(DC_INFRA) down --remove-orphans
	docker network rm $(NET) 2>/dev/null || true

up: compose-up ## Alias for compose-up
up-hc: compose-up-hc ## Alias for compose-up-hc
up-sc: compose-up-sc ## Alias for compose-up-sc
down: compose-down ## Alias for compose-down

build: build-hc ## Build healthcare images
build-hc: ## Build healthcare images
	$(DC_HC) build

build-sc: ## Build supply-chain images
	$(DC_SC) build

build-all: build-hc build-sc ## Build all domain images

restart: ## Restart healthcare services
	$(DC_HC) down && $(DC_HC) up -d

restart-sc: ## Restart supply-chain services
	$(DC_SC) down && $(DC_SC) up -d

clean: ## Stop stacks, remove volumes, and prune Docker
	$(DC_SC) down -v --remove-orphans 2>/dev/null || true
	$(DC_HC) down -v --remove-orphans 2>/dev/null || true
	$(DC_INFRA) down -v --remove-orphans 2>/dev/null || true
	docker network rm $(NET) 2>/dev/null || true
	docker system prune -f

fresh: clean compose-up pull-model ## Recreate the Compose stack and pull Ollama model

pull-model: ## Pull the Ollama model
	docker exec infra-ollama ollama pull llama3.1

# ---------------------------------------------------------------------------
# Docker Compose: status and service access
# ---------------------------------------------------------------------------

ps: ## Show running containers
	@docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | sort

logs: ## Tail healthcare logs
	$(DC_HC) logs -f --tail 20

logs-sc: ## Tail supply-chain logs
	$(DC_SC) logs -f --tail 20 sc-producer sc-flink-app sc-agent-service

neo4j-hc: ## Open the healthcare Neo4j shell
	docker exec -it healthcare-neo4j cypher-shell -u neo4j -p healthcare123

neo4j-sc: ## Open the supply-chain Neo4j shell
	docker exec -it supplychain-neo4j cypher-shell -u neo4j -p supplychain123

qdrant-hc: ## Show the healthcare Qdrant collection
	@curl -s http://localhost:6333/collections/healthcare_events | python3 -m json.tool

qdrant-sc: ## Show the supply-chain Qdrant collection
	@curl -s http://localhost:6335/collections/supplychain_events | python3 -m json.tool

api-hc: ## Check the healthcare agent health
	@curl -s http://localhost:8000/health | python3 -m json.tool

api-sc: ## Check the supply-chain agent health
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

shell-kafka: ## Open a Kafka shell
	docker exec -it infra-kafka bash

# ---------------------------------------------------------------------------
# Web application
# ---------------------------------------------------------------------------

web-hc-dev: ## Start the healthcare web UI development server
	cd $(HC_WEB) && npm install && VITE_API_BASE_URL=/api npm run dev

web-hc-test: ## Run healthcare web UI tests
	cd $(HC_WEB) && npm ci && npm run typecheck && npm test

web-hc-build: ## Build the healthcare web UI
	cd $(HC_WEB) && npm ci && npm run build

# ---------------------------------------------------------------------------
# Validation and tests
# ---------------------------------------------------------------------------

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

lint: ## Run Ruff
	uv run ruff check packages domains scripts

test-core: ## Run agent-core tests
	cd packages/agent-core && uv run --package agent-core pytest --tb=short

test-hc: ## Run healthcare tests
	cd domains/healthcare/agent-service && uv run --package healthcare-agent-service pytest --tb=short

test-sc: ## Run supply-chain tests
	cd domains/supply-chain/agent-service && uv run --package supply-chain-agent-service pytest --tb=short

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

# ---------------------------------------------------------------------------
# Kubernetes: Minikube development
# ---------------------------------------------------------------------------

minikube-up: ## Start Minikube and deploy the development Helm release
	MINIKUBE_DRIVER=docker $(KUBE_SETUP)

minikube-down: ## Remove the development Helm release
	helm uninstall $(KUBE_RELEASE) -n $(KUBE_NAMESPACE) || true

minikube-ports: ## Start Minikube service port-forwards
	$(MAKE) helm-ports

minikube-ports-stop: ## Stop Minikube service port-forwards
	$(MAKE) helm-ports-stop

helm-dev: minikube-up ## Alias for minikube-up
helm-dev-down: minikube-down ## Alias for minikube-down

helm-ports: ## Start Minikube service port-forwards
	@pkill -f "port-forward" 2>/dev/null || true
	@kubectl -n $(KUBE_NAMESPACE) port-forward svc/agent-service 8000:8000 >/dev/null 2>&1 &
	@kubectl -n $(KUBE_NAMESPACE) port-forward svc/provider-web 8088:80 >/dev/null 2>&1 &
	@kubectl -n $(KUBE_NAMESPACE) port-forward svc/neo4j 7474:7474 7687:7687 >/dev/null 2>&1 &
	@kubectl -n $(KUBE_NAMESPACE) port-forward svc/qdrant 6333:6333 >/dev/null 2>&1 &
	@kubectl -n $(KUBE_NAMESPACE) port-forward svc/patient-memory-postgres 5432:5432 >/dev/null 2>&1 &
	@kubectl -n $(KUBE_NAMESPACE) port-forward svc/conduktor-console 9080:8080 >/dev/null 2>&1 &
	@sleep 2
	@echo "Agent API: http://localhost:8000"
	@echo "Web UI: http://localhost:8088"
	@echo "Neo4j: http://localhost:7474"
	@echo "Qdrant: http://localhost:6333/dashboard"
	@echo "Patient memory PostgreSQL: postgresql://patient_memory:change_me@localhost:5432/patient_memory"
	@echo "Conduktor: http://localhost:9080"

helm-ports-stop: ## Stop Minikube service port-forwards
	@pkill -f "port-forward" 2>/dev/null || true
	@echo "Port-forwards stopped."

kube-status: ## Show the Helm release status
	@helm status $(KUBE_RELEASE) -n $(KUBE_NAMESPACE)

kube-pods: ## Show Minikube pods and services
	@kubectl -n $(KUBE_NAMESPACE) get pods,svc

kube-logs: ## Tail healthcare agent logs in Minikube
	@kubectl -n $(KUBE_NAMESPACE) logs deploy/agent-service --tail=50 -f

helm-lint: ## Lint and render development and production Helm values
	helm lint $(KUBE_CHART)
	helm template dev $(KUBE_CHART) -f $(KUBE_VALUES_DEV) >/dev/null
	helm template prd $(KUBE_CHART) -f $(KUBE_VALUES_PRD) >/dev/null
	@echo "Helm lint: OK"

helm-prd: ## Render production Helm manifests
	helm template healthcare $(KUBE_CHART) -f $(KUBE_VALUES_PRD)