{{- define "flink.labels" -}}
app.kubernetes.io/name: flink
app.kubernetes.io/instance: {{ .Release.Name }}
component: data-platform
{{- end -}}
