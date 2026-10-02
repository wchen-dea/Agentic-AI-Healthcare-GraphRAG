{{- define "mlflow.labels" -}}
app: mlflow
app.kubernetes.io/name: mlflow
app.kubernetes.io/instance: {{ .Release.Name }}
component: observability
{{- end -}}

{{- define "mlflow.selectorLabels" -}}
app: mlflow
{{- end -}}
