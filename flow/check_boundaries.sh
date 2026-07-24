#!/usr/bin/env bash
# Iron Rule 2 enforcement: role branches stay inside their directories.
# Usage: flow/check_boundaries.sh [base-ref]   (default: origin/main)
set -euo pipefail

base="${1:-origin/main}"
branch="$(git rev-parse --abbrev-ref HEAD)"
changed="$(git diff --name-only "${base}...HEAD" || true)"

deny() {
  local pattern="$1" label="$2"
  local hits
  hits="$(echo "$changed" | grep -E "$pattern" || true)"
  if [ -n "$hits" ]; then
    echo "BOUNDARY VIOLATION on '$branch': $label"
    echo "$hits" | sed 's/^/  - /'
    exit 1
  fi
}

case "$branch" in
  rtl/*)    deny '^hw/dv/'           "RTL role must not modify hw/dv/ (Iron Rule 2)" ;;
  dv/*)     deny '^hw/rtl/'             "DV role must not modify hw/rtl/ (Iron Rule 2)" ;;
  formal/*) deny '^hw/dv/'           "formal role must not modify sim testbenches" ;;
  sw/*)     deny '^hw/(rtl|dv)/'        "software role must not modify hw/rtl/ or hw/dv/" ;;
  pd/*)     deny '^hw/rtl/.*\.sv$'      "backend role must not modify RTL logic (file an issue)" ;;
  *)        echo "boundary check: branch '$branch' has no role restriction" ;;
esac

echo "boundary check OK for '$branch'"
