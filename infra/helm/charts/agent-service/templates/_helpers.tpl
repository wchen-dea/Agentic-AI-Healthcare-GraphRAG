{{- define "agent-service.fullname" -}}
{{ .Release.Name }}-agent-service
{{- end -}}

{{- define "agent-service.labels" -}}
app: agent-service
app.kubernetes.io/name: agent-service
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "agent-service.selectorLabels" -}}
app: agent-service
{{- end -}}
