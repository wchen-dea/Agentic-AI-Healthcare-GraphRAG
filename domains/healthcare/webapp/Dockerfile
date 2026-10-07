# Build context: repository root (see infra/compose/docker-compose.healthcare.yml).
FROM node:22-alpine AS build
# Mirror the repo layout so the contract-drift test can read the agent-service skills config.
WORKDIR /src/domains/healthcare/webapp
COPY domains/healthcare/webapp/package.json domains/healthcare/webapp/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY domains/healthcare/webapp/ ./
COPY domains/healthcare/agent-service/src/healthcare_agent/config/skills_layer.json /src/domains/healthcare/agent-service/src/healthcare_agent/config/skills_layer.json
# Default API base baked into the bundle; users can override it at runtime in the UI settings.
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_CALLER_ID=dev-clinician
ARG VITE_CALLER_ROLE=generation
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_CALLER_ID=${VITE_CALLER_ID}
ENV VITE_CALLER_ROLE=${VITE_CALLER_ROLE}
RUN npm test && npm run build

FROM nginx:alpine
COPY infra/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/domains/healthcare/webapp/dist /usr/share/nginx/html
