#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

MARKDOWN_TARGETS=(
  "README.md"
  "docs/**/*.md"
  "deploy/**/*.md"
  "mcp-server/**/*.md"
)

if command -v markdownlint >/dev/null 2>&1; then
  markdownlint "${MARKDOWN_TARGETS[@]}"
  exit 0
fi

if command -v markdownlint-cli2 >/dev/null 2>&1; then
  markdownlint-cli2 "${MARKDOWN_TARGETS[@]}"
  exit 0
fi

if command -v npx >/dev/null 2>&1; then
  npx --yes markdownlint-cli2 "${MARKDOWN_TARGETS[@]}"
  exit 0
fi

docker run --rm \
  -v "$ROOT_DIR:/workdir" \
  -w /workdir \
  node:20-alpine \
  sh -lc 'npx --yes markdownlint-cli2 README.md docs/**/*.md deploy/**/*.md mcp-server/**/*.md'