#!/usr/bin/env bash
# Validates the deploy plumbing without building or pushing anything.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0

need_file() {
  [ -f "$ROOT/$1" ] || { echo "MISSING FILE: $1"; fail=1; }
}
need_text() {
  grep -q -- "$2" "$ROOT/$1" || { echo "MISSING IN $1: $2"; fail=1; }
}
forbid_text() {
  if grep -q -- "$2" "$ROOT/$1"; then echo "FORBIDDEN IN $1: $2"; fail=1; fi
}

need_file backend/Dockerfile
need_file backend/Dockerfile.dev
need_file backend/.env.example
need_file frontend/Dockerfile
need_file docker-compose.yml
need_file cloudbuild.yaml

need_text backend/Dockerfile 'PYTHONPATH=/app/src'
need_text backend/Dockerfile 'EXPOSE 8000'
need_text frontend/Dockerfile 'PORT=3001'
need_text frontend/Dockerfile 'NEXT_PUBLIC_API_URL'
need_text cloudbuild.yaml '_API_HOST'
need_text docker-compose.yml 'postgres:16-alpine'

# Public repo: the env template must never carry a usable secret.
forbid_text backend/.env.example 'sk_live'
forbid_text backend/.env.example 'whsec_live'
need_text backend/.env.example 'ACCOUNT_TOKEN_PEPPER=replace-me-locally-only'

if [ "$fail" -ne 0 ]; then
  echo "DEPLOY CHECK FAILED"
  exit 1
fi
echo "DEPLOY CHECK PASSED"
