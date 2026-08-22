{{- define "rag-api.fullname" -}}
{{ .Release.Name }}-rag-api
{{- end -}}

{{- define "rag-api.labels" -}}
app: rag-api
app.kubernetes.io/name: rag-api
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "rag-api.selectorLabels" -}}
app: rag-api
{{- end -}}
