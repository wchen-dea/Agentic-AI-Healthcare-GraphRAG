# Kubernetes Deployment

This bundle deploys the full platform stack to Kubernetes.

## Components

| Component | Manifest | Replicas | Purpose |
| --- | --- | --- | --- |
| Healthcare agents | `rag-api-deployment.yaml` | 2 (HPA: 2–6) | AI agents with embedded MCP at `/mcp` |
| Provider web | `provider-web-deployment.yaml` | 2 (HPA: 2–5) | Static frontend UI |
| Flink JobManager | `flink-jobmanager-deployment.yaml` | 1 | Shared Flink cluster coordinator |
| Flink TaskManager | `flink-taskmanager-deployment.yaml` | 2 | Shared Flink cluster workers |
| Flink job submit | `flink-job-submit.yaml` | Job | Healthcare PyFlink job submission |
| MLflow | `mlflow-deployment.yaml` | 1 | Agent tracing and evaluation (5Gi PVC) |

## Structure

- `base/`: all Kubernetes manifests + kustomization
- `ingress.example.yaml`: example ingress routes

## Platform Controls

- NetworkPolicy: default deny ingress for namespace
- NetworkPolicy: explicit allow for `rag-api` (8000), `provider-web` (80), `flink-jobmanager` (8081/6123), `mlflow` (5000)
- HPA: `rag-api` (2–6), `provider-web` (2–5)
- HPAs require metrics-server in the cluster

## Configuration Guidelines

- Use dedicated namespaces per environment with scoped RBAC.
- Replace example secret manifests with values from your cluster secret workflow.
- Pin image tags or digests and promote the same tested image between environments.
- Set ingress hosts, TLS certificates, and DNS records per environment.
- Review NetworkPolicy rules with ingress controller behavior.
- For production MLflow, replace SQLite backend with PostgreSQL and use object storage for artifacts.
- Add pod disruption budgets, resource requests and limits, and rollout strategy settings if your production platform standards require them.
- Forward logs, metrics, and audit events to centralized observability systems rather than relying only on in-cluster inspection.

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

## Optional Ingress

```bash
kubectl apply -f ingress.example.yaml
```

## Endpoint Expectations

- rag-api health: `/health`
- embedded MCP diagnostic: `/mcp/health`
- embedded MCP protocol: `/mcp`
- provider web: `/`
