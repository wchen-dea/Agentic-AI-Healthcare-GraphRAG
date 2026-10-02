{{- define "provider-web.labels" -}}
app: provider-web
app.kubernetes.io/name: provider-web
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "provider-web.selectorLabels" -}}
app: provider-web
{{- end -}}
