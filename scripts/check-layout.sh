#!/usr/bin/env bash
# Asserts the repository scaffold exists. Run from anywhere.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fail=0
for f in package.json pnpm-workspace.yaml .gitignore .nvmrc Makefile; do
  if [ ! -f "$ROOT/$f" ]; then
    echo "MISSING: $f"
    fail=1
  fi
done
grep -q '"name": "saiife-hub"' "$ROOT/package.json" || { echo "MISSING: package name saiife-hub"; fail=1; }
grep -q 'packages/\*' "$ROOT/pnpm-workspace.yaml" || { echo "MISSING: packages/* workspace"; fail=1; }
if [ "$fail" -ne 0 ]; then
  echo "LAYOUT CHECK FAILED"
  exit 1
fi
echo "LAYOUT CHECK PASSED"
