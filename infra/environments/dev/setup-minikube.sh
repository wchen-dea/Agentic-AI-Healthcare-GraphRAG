#!/usr/bin/env bash
set -euo pipefail
# Bootstrap local minikube dev environment using Helm.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
HELM_CHART="$INFRA_DIR/helm"
VALUES_FILE="$INFRA_DIR/helm/values-dev.yaml"
RELEASE_NAME="healthcare-dev"
NAMESPACE="healthcare-ai-dev"
MINIKUBE_CPUS="${MINIKUBE_CPUS:-4}"
MINIKUBE_MEMORY="${MINIKUBE_MEMORY:-16384}"
MINIKUBE_DRIVER="${MINIKUBE_DRIVER:-docker}"

echo "=== Minikube Dev Setup (Helm) ==="

# Start minikube unless both the node and the API server are already running.
# A running host with a stopped API server (for example after the minikube
# container was removed outside minikube) needs a restart or a full reset.
host_status="$(minikube status --format='{{.Host}}' 2>/dev/null || true)"
apiserver_status="$(minikube status --format='{{.APIServer}}' 2>/dev/null || true)"
if [ "$host_status" = "Running" ] && [ "$apiserver_status" = "Running" ]; then
  echo "Minikube already running."
else
  echo "Starting minikube (cpus=$MINIKUBE_CPUS, memory=${MINIKUBE_MEMORY}MB, driver=$MINIKUBE_DRIVER)..."
  if ! minikube start \
    --cpus="$MINIKUBE_CPUS" \
    --memory="$MINIKUBE_MEMORY" \
    --driver="$MINIKUBE_DRIVER" \
    --wait=all \
    --wait-timeout=5m0s; then
    cat >&2 <<'EOF'

minikube failed to start. The existing profile is likely stale or broken, for
example when the minikube container was deleted but its volume survived, or
when the profile was created with different CPU or memory settings.
Reset it with (this erases all in-cluster data):
  minikube delete && make minikube-up
EOF
    exit 1
  fi
fi

# Build images inside minikube's Docker daemon
REPO_ROOT="$(cd "$INFRA_DIR/.." && pwd)"
echo "Building images in minikube Docker..."
eval $(minikube docker-env)
docker build -q -f "$REPO_ROOT/domains/healthcare/agent-service/Dockerfile" -t ghcr.io/wchen-dea/agentic-ai-healthcare-graphrag-agent-service:latest "$REPO_ROOT"
docker build -q -f "$REPO_ROOT/domains/healthcare/data-pipelines/producer/Dockerfile" -t ghcr.io/wchen-dea/agentic-ai-healthcare-graphrag-producer:latest "$REPO_ROOT"
docker build -q -f "$REPO_ROOT/domains/healthcare/data-pipelines/flink-job/Dockerfile" -t ghcr.io/wchen-dea/agentic-ai-healthcare-graphrag-flink-healthcare:latest "$REPO_ROOT"
docker build -q --build-arg VITE_CALLER_ID="${VITE_CALLER_ID:-dev-clinician}" --build-arg VITE_CALLER_ROLE="${VITE_CALLER_ROLE:-generation}" --build-arg VITE_REQUEST_TIMEOUT_MS="${VITE_REQUEST_TIMEOUT_MS:-360000}" -f "$REPO_ROOT/domains/healthcare/webapp/Dockerfile" -t ghcr.io/wchen-dea/agentic-ai-healthcare-graphrag-provider-web:latest "$REPO_ROOT"
echo "Images built."

# Install or upgrade via Helm
echo "Installing Helm chart..."
LOCAL_VALUES="$INFRA_DIR/helm/values-dev.local.yaml"
LOCAL_ARGS=""
if [ ! -f "$LOCAL_VALUES" ]; then
  echo "Missing $LOCAL_VALUES; create it with NEO4J_PASSWORD, DATABRICKS_TOKEN, and MCP_AUTH_TOKEN." >&2
  exit 1
fi
LOCAL_ARGS="-f $LOCAL_VALUES"
for required in 'DATABRICKS_TOKEN' 'NEO4J_PASSWORD' 'MCP_AUTH_TOKEN'; do
  if ! grep -Eq "^[[:space:]]+$required:[[:space:]]*[^\"']+[^[:space:]]" "$LOCAL_VALUES"; then
    echo "$required must be set in $LOCAL_VALUES" >&2
    exit 1
  fi
done
pg_password_line="$(helm template "$RELEASE_NAME" "$HELM_CHART" -f "$VALUES_FILE" $LOCAL_ARGS \
  -s charts/agent-service/templates/patient-memory-postgres.yaml 2>/dev/null | grep 'POSTGRES_PASSWORD:' || true)"
if [ -z "$pg_password_line" ] || echo "$pg_password_line" | grep -Eq 'POSTGRES_PASSWORD:[[:space:]]*""'; then
  echo "agent-service.patientMemoryPostgres.password must be set in $LOCAL_VALUES" >&2
  echo "(nested under agent-service, matching the password in the database URLs)" >&2
  exit 1
fi
helm upgrade --install "$RELEASE_NAME" "$HELM_CHART" \
  -f "$VALUES_FILE" $LOCAL_ARGS \
  -n "$NAMESPACE" --create-namespace

# Wait for core services
echo "Waiting for pods..."
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=kafka --timeout=120s 2>/dev/null || true
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=neo4j --timeout=120s 2>/dev/null || true
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=qdrant --timeout=60s 2>/dev/null || true
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=agent-service --timeout=120s 2>/dev/null || true

echo
echo "=== Dev Environment Ready ==="
echo
echo "Credentials are loaded from the untracked values-dev.local.yaml file."
echo
echo "Access services (port-forward):"
echo "  kubectl -n $NAMESPACE port-forward svc/agent-service 8000:8000"
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
