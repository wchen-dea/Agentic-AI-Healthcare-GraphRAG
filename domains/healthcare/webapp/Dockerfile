# Build context: repository root (see container/docker-compose.healthcare.yml).
FROM node:22-alpine AS build
WORKDIR /app
COPY domains/healthcare/webapp/package.json domains/healthcare/webapp/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY domains/healthcare/webapp/ ./
# Default API base baked into the bundle; users can override it at runtime in the UI settings.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm test && npm run build

FROM nginx:alpine
COPY platform/shared/webapp/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
