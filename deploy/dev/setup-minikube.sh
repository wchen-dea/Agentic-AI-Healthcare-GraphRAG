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
MINIKUBE_MEMORY="${MINIKUBE_MEMORY:-8192}"
MINIKUBE_DRIVER="${MINIKUBE_DRIVER:-docker}"

echo "=== Minikube Dev Setup (Helm) ==="

# Start minikube if not running
if ! minikube status --format='{{.Host}}' 2>/dev/null | grep -q Running; then
  echo "Starting minikube (cpus=$MINIKUBE_CPUS, memory=${MINIKUBE_MEMORY}MB, driver=$MINIKUBE_DRIVER)..."
  minikube start --cpus="$MINIKUBE_CPUS" --memory="$MINIKUBE_MEMORY" --driver="$MINIKUBE_DRIVER"
else
  echo "Minikube already running."
fi

# Install or upgrade via Helm
echo "Installing Helm chart..."
helm upgrade --install "$RELEASE_NAME" "$HELM_CHART" \
  -f "$VALUES_FILE" \
  -n "$NAMESPACE" --create-namespace

# Wait for core services
echo "Waiting for pods..."
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=rag-api --timeout=120s 2>/dev/null || true
kubectl -n "$NAMESPACE" wait --for=condition=Ready pod -l app=mlflow --timeout=120s 2>/dev/null || true

echo
echo "=== Dev Environment Ready ==="
echo
echo "Access services:"
echo "  RAG API:  http://\$(minikube ip):30800"
echo
echo "Tear down:  helm uninstall $RELEASE_NAME -n $NAMESPACE"
echo "Full reset: minikube delete"
