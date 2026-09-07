#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
checker="$repo_root/flow/check_boundaries.sh"
tmp_root="$(mktemp -d "${TMPDIR:-/tmp}/openchip-boundaries.XXXXXX")"
trap 'rm -rf "$tmp_root"' EXIT

passes=0

new_repo() {
  repo="$tmp_root/$1"
  mkdir -p "$repo"
  git -C "$repo" init -q
  git -C "$repo" config user.name "Boundary Test"
  git -C "$repo" config user.email "boundary-test@example.invalid"
  printf 'fixture\n' > "$repo/README.md"
  git -C "$repo" add README.md
  git -C "$repo" commit -q -m base
  base_commit="$(git -C "$repo" rev-parse HEAD)"
}

commit_file() {
  path="$1"
  mkdir -p "$repo/$(dirname "$path")"
  printf 'fixture\n' > "$repo/$path"
  git -C "$repo" add "$path"
  git -C "$repo" commit -q -m "change $path"
}

run_check() {
  (cd "$repo" && bash "$checker" "$@")
}

expect_pass() {
  label="$1"
  shift
  if output="$("$@" 2>&1)"; then
    passes=$((passes + 1))
    printf 'ok %d - %s\n' "$passes" "$label"
  else
    printf 'not ok - %s\n%s\n' "$label" "$output" >&2
    exit 1
  fi
}

expect_pass_with() {
  label="$1"
  expected="$2"
  shift 2
  if ! output="$("$@" 2>&1)"; then
    printf 'not ok - %s\n%s\n' "$label" "$output" >&2
    exit 1
  fi
  if ! printf '%s\n' "$output" | grep -F "$expected" >/dev/null; then
    printf 'not ok - %s (missing %s)\n%s\n' "$label" "$expected" "$output" >&2
    exit 1
  fi
  passes=$((passes + 1))
  printf 'ok %d - %s\n' "$passes" "$label"
}

expect_fail() {
  label="$1"
  expected="$2"
  shift 2
  if output="$("$@" 2>&1)"; then
    printf 'not ok - %s (unexpected pass)\n%s\n' "$label" "$output" >&2
    exit 1
  fi
  if ! printf '%s\n' "$output" | grep -F "$expected" >/dev/null; then
    printf 'not ok - %s (missing %s)\n%s\n' "$label" "$expected" "$output" >&2
    exit 1
  fi
  passes=$((passes + 1))
  printf 'ok %d - %s\n' "$passes" "$label"
}

new_repo normal_forbidden
git -C "$repo" checkout -q -b rtl/normal-forbidden
commit_file hw/dv/demo/test_demo.py
expect_fail "normal RTL branch rejects a DV change" "BOUNDARY VIOLATION" \
  run_check "$base_commit"

new_repo dv_forbidden
git -C "$repo" checkout -q -b dv/forbidden
commit_file hw/rtl/demo.sv
expect_fail "DV branch rejects an RTL change" "BOUNDARY VIOLATION" \
  run_check "$base_commit"

new_repo formal_forbidden
git -C "$repo" checkout -q -b formal/forbidden
commit_file hw/dv/demo/test_demo.py
expect_fail "formal branch rejects a DV change" "BOUNDARY VIOLATION" \
  run_check "$base_commit"

new_repo sw_forbidden
git -C "$repo" checkout -q -b sw/forbidden
commit_file hw/rtl/demo.sv
expect_fail "software branch rejects a hardware implementation change" \
  "BOUNDARY VIOLATION" run_check "$base_commit"

new_repo pd_forbidden
git -C "$repo" checkout -q -b pd/forbidden
commit_file hw/rtl/demo.sv
expect_fail "backend branch rejects an RTL source change" "BOUNDARY VIOLATION" \
  run_check "$base_commit"

new_repo detached_forbidden
git -C "$repo" checkout -q -b rtl/detached-forbidden
commit_file hw/dv/demo/test_demo.py
git -C "$repo" checkout -q --detach HEAD
expect_fail "detached PR checkout uses explicit RTL branch context" "BOUNDARY VIOLATION" \
  run_check "$base_commit" rtl/detached-forbidden

new_repo allowed
git -C "$repo" checkout -q -b rtl/allowed
commit_file hw/rtl/demo.sv
expect_pass "RTL branch accepts an RTL change" run_check "$base_commit"

new_repo invalid_base
git -C "$repo" checkout -q -b rtl/invalid-base
commit_file hw/rtl/demo.sv
expect_fail "unavailable base ref fails closed" "does not resolve to a commit" \
  run_check refs/heads/definitely-missing
expect_fail "empty base ref fails closed" "base ref must not be empty" \
  run_check "" rtl/invalid-base
expect_fail "invalid explicit branch context fails closed" "invalid role branch" \
  run_check "$base_commit" "rtl/invalid branch"

new_repo unrelated_base
empty_tree="$(git -C "$repo" mktree </dev/null)"
unrelated_commit="$(printf 'unrelated base\n' | git -C "$repo" commit-tree "$empty_tree")"
expect_fail "base without a merge point fails closed" "unable to compare" \
  run_check "$unrelated_commit" rtl/unrelated-base

new_repo detached_without_context
git -C "$repo" checkout -q --detach HEAD
expect_fail "detached checkout without explicit context fails closed" \
  "detached HEAD requires an explicit role branch" run_check "$base_commit"

new_repo ordinary_branch
git -C "$repo" checkout -q -b docs/ordinary
commit_file hw/dv/demo/test_demo.py
expect_pass_with "ordinary branch remains explicitly unrestricted" \
  "has no recognized role restriction" run_check "$base_commit"

new_repo forbidden_deletion
commit_file hw/dv/demo/test_demo.py
base_commit="$(git -C "$repo" rev-parse HEAD)"
git -C "$repo" checkout -q -b rtl/delete-forbidden
git -C "$repo" rm -q hw/dv/demo/test_demo.py
git -C "$repo" commit -q -m "delete forbidden path"
expect_fail "forbidden deletion remains visible" "hw/dv/demo/test_demo.py" \
  run_check "$base_commit"

new_repo forbidden_rename
commit_file hw/dv/demo/test_demo.py
base_commit="$(git -C "$repo" rev-parse HEAD)"
git -C "$repo" checkout -q -b rtl/rename-forbidden
mkdir -p "$repo/hw/rtl"
git -C "$repo" mv hw/dv/demo/test_demo.py hw/rtl/demo.sv
git -C "$repo" commit -q -m "rename forbidden source path"
expect_fail "forbidden rename source remains visible" "hw/dv/demo/test_demo.py" \
  run_check "$base_commit"

new_repo unusual_forbidden_path
git -C "$repo" checkout -q -b rtl/unusual-forbidden-path
commit_file $'hw/dv/demo/test\nnewline.py'
expect_fail "unusual forbidden path cannot evade matching" "BOUNDARY VIOLATION" \
  run_check "$base_commit"

printf '1..%d\n' "$passes"
