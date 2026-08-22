#!/usr/bin/env bash
set -euo pipefail
# Bootstrap local minikube dev environment using Helm.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
HELM_CHART="$DEPLOY_DIR/helm"
VALUES_FILE="$DEPLOY_DIR/helm/values-dev.yaml"
RELEASE_NAME="healthcare-dev"
NAMESPACE="healthcare-ai-dev"
MINIKUBE_CPUS="${MINIKUBE_CPUS:-4}"
MINIKUBE_MEMORY="${MINIKUBE_MEMORY:-16384}"
MINIKUBE_DRIVER="${MINIKUBE_DRIVER:-docker}"

echo "=== Minikube Dev Setup (Helm) ==="

# Start minikube if not running
if ! minikube status --format='{{.Host}}' 2>/dev/null | grep -q Running; then
  echo "Starting minikube (cpus=$MINIKUBE_CPUS, memory=${MINIKUBE_MEMORY}MB, driver=$MINIKUBE_DRIVER)..."
  minikube start \
    --cpus="$MINIKUBE_CPUS" \
    --memory="$MINIKUBE_MEMORY" \
    --driver="$MINIKUBE_DRIVER" \
    --wait=all \
    --wait-timeout=5m0s
else
  echo "Minikube already running."
fi

# Build images inside minikube's Docker daemon
REPO_ROOT="$(cd "$DEPLOY_DIR/.." && pwd)"
echo "Building images in minikube Docker..."
eval $(minikube docker-env)
docker build -q -f "$REPO_ROOT/domains/healthcare/agents/Dockerfile" -t ghcr.io/wchen-dea/agentic-ai-healthcare-graphrag-rag-api:latest "$REPO_ROOT"
docker build -q -f "$REPO_ROOT/data-platform/healthcare/producer/Dockerfile" -t ghcr.io/wchen-dea/agentic-ai-healthcare-graphrag-producer:latest "$REPO_ROOT"
docker build -q -f "$REPO_ROOT/data-platform/healthcare/flink-app/Dockerfile" -t ghcr.io/wchen-dea/agentic-ai-healthcare-graphrag-flink-healthcare:latest "$REPO_ROOT"
docker build -q -f "$REPO_ROOT/domains/healthcare/webapp/Dockerfile" -t ghcr.io/wchen-dea/agentic-ai-healthcare-graphrag-provider-web:latest "$REPO_ROOT"
echo "Images built."

# Install or upgrade via Helm
echo "Installing Helm chart..."
helm upgrade --install "$RELEASE_NAME" "$HELM_CHART" \
  -f "$VALUES_FILE" \
  -n "$NAMESPACE" --create-namespace

# Wait for core services
echo "Waiting for pods..."
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=kafka --timeout=120s 2>/dev/null || true
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=neo4j --timeout=120s 2>/dev/null || true
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=qdrant --timeout=60s 2>/dev/null || true
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=ollama --timeout=60s 2>/dev/null || true
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=rag-api --timeout=120s 2>/dev/null || true

# Pull LLM model
echo "Pulling LLM model (qwen2.5:1.5b)..."
OLLAMA_POD=$(kubectl -n "$NAMESPACE" get pod -l app=ollama -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [[ -n "$OLLAMA_POD" ]]; then
  kubectl -n "$NAMESPACE" exec "$OLLAMA_POD" -- ollama pull qwen2.5:1.5b 2>/dev/null || echo "Model pull skipped (pod not ready)"
fi

echo
echo "=== Dev Environment Ready ==="
echo
echo "Access services (port-forward):"
echo "  kubectl -n $NAMESPACE port-forward svc/rag-api 8000:8000"
echo "  kubectl -n $NAMESPACE port-forward svc/provider-web 8088:80"
echo "  kubectl -n $NAMESPACE port-forward svc/neo4j 7474:7474 7687:7687"
echo "  kubectl -n $NAMESPACE port-forward svc/qdrant 6333:6333"
echo "  kubectl -n $NAMESPACE port-forward svc/conduktor-console 9080:8080"
echo
echo "Or use NodePort:"
echo "  RAG API:  http://\$(minikube ip):30800"
echo
echo "Tear down:  helm uninstall $RELEASE_NAME -n $NAMESPACE"
echo "Full reset: minikube delete"
