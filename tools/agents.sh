#!/usr/bin/env bash
# OpenChip agent bootstrap — CLI-agnostic.
#
#   tools/agents.sh scan          which coding-agent CLIs are installed here
#   tools/agents.sh sync          create skill entrypoints for detected CLIs
#   tools/agents.sh sync --all    create them for every supported CLI
#
# The canonical rules live in AGENTS.md and .agents/skills/<role>/SKILL.md.
# Every CLI below reads AGENTS.md; `sync` additionally exposes the role skills
# in each CLI's own skills directory so they are auto-discovered, not just
# reachable by path.
set -euo pipefail

cd "$(dirname "$0")/.."
CANON=".agents/skills"

# name | command | skills dir ("-" = reads AGENTS.md only, nothing to mirror)
CLIS=(
  "Claude Code|claude|.claude/skills"
  "Codex|codex|-"
  "Gemini CLI|gemini|-"
  "GitHub Copilot CLI|copilot|-"
  "Cursor|cursor-agent|.cursor/skills"
  "Antigravity CLI|agy|.antigravitycli/skills"
  "Grok CLI|grok|.grok/skills"
  "Qwen Code|qwen|.qwen/skills"
  "OpenCode|opencode|.opencode/skills"
  "Kimi CLI|kimi|.kimi/skills"
)

roles() { for d in "$CANON"/*/; do basename "$d"; done; }

# Claude Code is the reference CLI: its entrypoints are committed, so a fresh
# clone works with no bootstrap step at all.
always_sync=".claude/skills"

link() { # link <target-relative-to-linkdir> <linkpath>
  ln -sfn "$1" "$2" 2>/dev/null || cp -R "$(dirname "$2")/$1" "$2"
}

sync_cli() {
  local dir="$1" role
  for role in $(roles); do
    mkdir -p "$dir/$role"
    link "../../../$CANON/$role/SKILL.md" "$dir/$role/SKILL.md"
    if [ -d "$CANON/$role/references" ]; then
      link "../../../$CANON/$role/references" "$dir/$role/references"
    elif [ -L "$dir/$role/references" ]; then
      rm "$dir/$role/references"
    fi
  done
  echo "  synced $dir  ($(roles | wc -l | tr -d ' ') roles)"
}

case "${1:-scan}" in
  scan)
    echo "Coding agents available in this workspace:"
    found=0
    for entry in "${CLIS[@]}"; do
      IFS='|' read -r name cmd dir <<<"$entry"
      if command -v "$cmd" >/dev/null 2>&1; then
        found=$((found + 1))
        printf '  %-22s %-14s %s\n' "$name" "$cmd" \
          "$([ "$dir" = "-" ] && echo "AGENTS.md" || echo "AGENTS.md + $dir")"
      fi
    done
    [ "$found" -eq 0 ] && echo "  (none detected on PATH)"
    echo
    echo "All of them read AGENTS.md, which indexes the $(roles | wc -l | tr -d ' ') role skills in $CANON/."
    echo "Run 'make agents-sync' to expose those skills to every detected CLI."
    ;;
  sync)
    echo "Syncing skill entrypoints from $CANON/ ..."
    for entry in "${CLIS[@]}"; do
      IFS='|' read -r name cmd dir <<<"$entry"
      [ "$dir" = "-" ] && continue
      if [ "${2:-}" = "--all" ] || [ "$dir" = "$always_sync" ] || command -v "$cmd" >/dev/null 2>&1; then
        sync_cli "$dir"
      fi
    done
    ;;
  *)
    echo "usage: tools/agents.sh [scan|sync [--all]]" >&2
    exit 2
    ;;
esac
