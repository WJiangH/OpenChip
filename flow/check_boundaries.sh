#!/usr/bin/env bash
# Iron Rule 2 enforcement for recognized role branches.
# Usage: flow/check_boundaries.sh [base-ref] [role-branch]
#   base-ref defaults to origin/main.
#   role-branch defaults to the current branch, but detached checkouts must pass it.
# Branches without a recognized role prefix have no role-specific restriction.
set -euo pipefail

if [ "$#" -gt 2 ]; then
  echo "boundary check: expected at most 2 arguments: [base-ref] [role-branch]" >&2
  exit 2
fi

base="${1-origin/main}"
if [ -z "$base" ]; then
  echo "boundary check: base ref must not be empty" >&2
  exit 2
fi

if [ "$#" -ge 2 ]; then
  branch="$2"
else
  if ! branch="$(git symbolic-ref --quiet --short HEAD)"; then
    echo "boundary check: detached HEAD requires an explicit role branch" >&2
    exit 2
  fi
fi

if [ -z "$branch" ] || [ "$branch" = "HEAD" ] ||
   ! git check-ref-format --branch "$branch" >/dev/null 2>&1; then
  echo "boundary check: invalid role branch '$branch'" >&2
  exit 2
fi

if ! base_commit="$(git rev-parse --verify --end-of-options "${base}^{commit}" 2>/dev/null)"; then
  echo "boundary check: base ref '$base' does not resolve to a commit" >&2
  exit 2
fi
if ! head_commit="$(git rev-parse --verify --end-of-options 'HEAD^{commit}' 2>/dev/null)"; then
  echo "boundary check: HEAD does not resolve to a commit" >&2
  exit 2
fi

changed_file="$(mktemp "${TMPDIR:-/tmp}/openchip-boundaries.XXXXXX")"
trap 'rm -f "$changed_file"' EXIT HUP INT TERM
if ! git diff --name-only --no-renames -z \
     "${base_commit}...${head_commit}" > "$changed_file"; then
  echo "boundary check: unable to compare '$base' with HEAD" >&2
  exit 2
fi

deny() {
  local pattern="$1" label="$2"
  local path violated=0
  while IFS= read -r -d '' path; do
    if [[ "$path" =~ $pattern ]]; then
      if [ "$violated" -eq 0 ]; then
        echo "BOUNDARY VIOLATION on '$branch': $label"
      fi
      printf '  - %q\n' "$path"
      violated=1
    fi
  done < "$changed_file"
  if [ "$violated" -ne 0 ]; then
    exit 1
  fi
}

case "$branch" in
  rtl/*)    deny '^hw/dv/'           "RTL role must not modify hw/dv/ (Iron Rule 2)" ;;
  dv/*)     deny '^hw/rtl/'             "DV role must not modify hw/rtl/ (Iron Rule 2)" ;;
  formal/*) deny '^hw/dv/'           "formal role must not modify sim testbenches" ;;
  sw/*)     deny '^hw/(rtl|dv)/'        "software role must not modify hw/rtl/ or hw/dv/" ;;
  pd/*)     deny '^hw/rtl/.*\.sv$'      "backend role must not modify RTL logic (file an issue)" ;;
  *)        echo "boundary check: branch '$branch' has no recognized role restriction" ;;
esac

echo "boundary check OK for '$branch'"
