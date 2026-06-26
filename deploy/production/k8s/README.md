# Kubernetes Deployment (AI Components Only)

This bundle deploys only AI app deliverables from this repository.

In scope:

- rag-api (includes embedded FastMCP endpoint at `/mcp`)
- provider-web
- optional standalone mcp-server (separate manifests)

Out of scope and externally managed:

- source data systems and upstream environments
- Confluent Kafka (managed by operations)
- Apache Flink on AWS EKS/Kubernetes (managed independently)

## Structure

- `base/`: rag-api and provider-web Kubernetes manifests + kustomization
- `optional-mcp/`: standalone MCP deployment manifests + kustomization
- `ingress.example.yaml`: example ingress routes for AI endpoints

Minimal platform controls included:

- NetworkPolicy set: default deny ingress for namespace.
- NetworkPolicy set: explicit ingress allow for `rag-api` (8000), `provider-web` (80), and optional `mcp-server` (8010).
- HorizontalPodAutoscaler set: `rag-api` (min 2, max 6).
- HorizontalPodAutoscaler set: `provider-web` (min 2, max 5).
- HorizontalPodAutoscaler set: optional `mcp-server` (min 2, max 4).

Note: HPAs require metrics-server (or compatible metrics pipeline) in the cluster.

## Deploy Base (rag-api + provider-web)

1. Create secret manifests from examples:

```bash
cp base/rag-api-secret.example.yaml base/rag-api-secret.yaml
# edit base/rag-api-secret.yaml values
```

1. Apply namespace and base resources:

```bash
kubectl apply -k base
kubectl apply -f base/rag-api-secret.yaml
```

## Deploy Optional Standalone MCP

1. Create MCP secret manifest:

```bash
cp optional-mcp/mcp-secret.example.yaml optional-mcp/mcp-secret.yaml
# edit optional-mcp/mcp-secret.yaml values
```

1. Apply resources:

```bash
kubectl apply -k optional-mcp
kubectl apply -f optional-mcp/mcp-secret.yaml
```

## Optional Ingress

```bash
kubectl apply -f ingress.example.yaml
```

## Endpoint Expectations

- rag-api health: `/health`
- embedded MCP diagnostic: `/mcp/health`
- embedded MCP protocol: `/mcp`
- provider web: `/`
