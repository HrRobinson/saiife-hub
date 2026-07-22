#!/usr/bin/env bash
# Terraform is AUTHORED here, never applied. This check enforces the public-repo
# rules: no real project ids or hostnames, no secret VALUES, and no apply step.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA="$ROOT/infra"
fail=0

for f in main.tf variables.tf 01_artifact_registry.tf 02_database.tf 03_secrets.tf \
         04_run_services.tf 05_run_migrate_job.tf 06_iam.tf outputs.tf README.md; do
  [ -f "$INFRA/$f" ] || { echo "MISSING FILE: infra/$f"; fail=1; }
done

# Environment-identifying variables must be REQUIRED (no default) so nothing real
# is committed.
for var in project_id region base_domain; do
  if ! grep -A4 "variable \"$var\"" "$INFRA/variables.tf" | grep -q "REQUIRED"; then
    echo "variable $var must be documented REQUIRED with no default"; fail=1
  fi
  if grep -A4 "variable \"$var\"" "$INFRA/variables.tf" | grep -q "default"; then
    echo "variable $var must NOT have a default"; fail=1
  fi
done

# Never a secret VALUE in Terraform — containers only.
if grep -rn "secret_data" "$INFRA" | grep -v "^.*#" | grep -q .; then
  echo "FORBIDDEN: infra must create secret CONTAINERS only, never versions"; fail=1
fi

# No apply automation may exist in this repo. This checker is excluded because it
# necessarily contains the very string it searches for.
if grep -rln "terraform apply" "$ROOT" \
     --include="*.sh" --include="*.yaml" --include="*.yml" --include="Makefile" \
     --exclude="check-infra.sh" | grep -q .; then
  echo "FORBIDDEN: this round authors Terraform, it never applies it"; fail=1
fi

grep -q "authored" "$INFRA/README.md" || { echo "README must state infra is authored, not applied"; fail=1; }

if [ "$fail" -ne 0 ]; then
  echo "INFRA CHECK FAILED"
  exit 1
fi
echo "INFRA CHECK PASSED"
