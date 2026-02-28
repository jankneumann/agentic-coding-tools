#!/usr/bin/env bash
set -euo pipefail

# fetch-vendor-skills.sh — Clone external skill repositories and extract
# their skill directories into skills/ so that install.sh auto-discovers them.
#
# Usage:
#   ./fetch-vendor-skills.sh              # Fetch all vendor skills
#   ./fetch-vendor-skills.sh --clean      # Remove vendor skills before fetching
#   ./fetch-vendor-skills.sh --list       # List configured vendor skills
#
# Each vendor entry maps a git repo + source path to a local skill directory name.
# The fetched content is committed alongside our own skills so install.sh works
# without network access. Re-run this script to update from upstream.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMPDIR_BASE="${TMPDIR:-/tmp}"
CLEAN=0
LIST_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean)  CLEAN=1; shift ;;
    --list)   LIST_ONLY=1; shift ;;
    -h|--help)
      sed -n '3,/^$/s/^# \?//p' "$0"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ── Vendor registry ────────────────────────────────────────────────────────
# Format: "repo_url | source_path_in_repo | local_skill_name"
#
# source_path_in_repo is relative to the repo root and should be a directory
# containing SKILL.md. Use "+" to fetch multiple skills from one repo
# (separate entries share the clone cache).

VENDORS=(
  "https://github.com/neondatabase/agent-skills  | skills/neon-postgres                              | neon-postgres"
  "https://github.com/neondatabase/agent-skills  | skills/claimable-postgres                         | claimable-postgres"
  "https://github.com/neondatabase/agent-skills  | plugins/neon-postgres/mcp.json                    | neon-postgres/.mcp/mcp.json"
  "https://github.com/railwayapp/railway-skills  | plugins/railway/skills/use-railway                | use-railway"
  "https://github.com/supabase/agent-skills      | skills/supabase-postgres-best-practices           | supabase-postgres-best-practices"
)

# ── Helpers ────────────────────────────────────────────────────────────────

declare -A CLONE_CACHE  # repo_url → local clone path

parse_entry() {
  local entry="$1"
  REPO_URL="$(echo "$entry" | cut -d'|' -f1 | xargs)"
  SRC_PATH="$(echo "$entry" | cut -d'|' -f2 | xargs)"
  LOCAL_NAME="$(echo "$entry" | cut -d'|' -f3 | xargs)"
}

# Pre-clone all unique repos so we don't clone the same repo multiple times
clone_all_repos() {
  local -A seen
  for entry in "${VENDORS[@]}"; do
    parse_entry "$entry"
    if [[ -z "${seen[$REPO_URL]:-}" ]]; then
      seen[$REPO_URL]=1
      local clone_dir
      clone_dir="$(mktemp -d "$TMPDIR_BASE/vendor-skill-XXXXXX")"
      echo "  clone  $REPO_URL"
      git clone --depth 1 --quiet "$REPO_URL" "$clone_dir"
      CLONE_CACHE[$REPO_URL]="$clone_dir"
    fi
  done
}

vendor_skill_dirs() {
  local -A seen
  for entry in "${VENDORS[@]}"; do
    parse_entry "$entry"
    # Extract the top-level local skill directory name
    local top_dir="${LOCAL_NAME%%/*}"
    if [[ -z "${seen[$top_dir]:-}" ]]; then
      seen[$top_dir]=1
      echo "$top_dir"
    fi
  done
}

# ── List mode ──────────────────────────────────────────────────────────────

if [[ $LIST_ONLY -eq 1 ]]; then
  echo "Configured vendor skills:"
  for entry in "${VENDORS[@]}"; do
    parse_entry "$entry"
    printf "  %-35s <- %s : %s\n" "$LOCAL_NAME" "$REPO_URL" "$SRC_PATH"
  done
  exit 0
fi

# ── Clean mode ─────────────────────────────────────────────────────────────

AGENT_SKILL_DIRS=(".claude/skills" ".codex/skills" ".gemini/skills")

REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ $CLEAN -eq 1 ]]; then
  echo "Cleaning vendor skills..."
  for dir in $(vendor_skill_dirs); do
    # Remove canonical source in skills/
    target="$SCRIPT_DIR/$dir"
    if [[ -d "$target" ]]; then
      echo "  rm    skills/$dir"
      rm -rf "$target"
    fi
    # Remove installed copies from agent config directories
    for agent_dir in "${AGENT_SKILL_DIRS[@]}"; do
      installed="$REPO_ROOT/$agent_dir/$dir"
      if [[ -e "$installed" || -L "$installed" ]]; then
        echo "  rm    $agent_dir/$dir"
        rm -rf "$installed"
      fi
    done
  done
fi

# ── Fetch and extract ──────────────────────────────────────────────────────

echo "Fetching vendor skills..."
clone_all_repos

fetched=0
for entry in "${VENDORS[@]}"; do
  parse_entry "$entry"

  clone_dir="${CLONE_CACHE[$REPO_URL]}"
  src="$clone_dir/$SRC_PATH"
  dest="$SCRIPT_DIR/$LOCAL_NAME"

  if [[ ! -e "$src" ]]; then
    echo "  WARN  $SRC_PATH not found in $REPO_URL — skipping" >&2
    continue
  fi

  # Handle file vs directory sources
  if [[ -f "$src" ]]; then
    # Single file — ensure parent directory exists
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    echo "  file  $LOCAL_NAME"
  elif [[ -d "$src" ]]; then
    # Directory — update in place (no delete; only add/overwrite files)
    mkdir -p "$dest"
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --checksum \
        --exclude='.git' \
        --exclude='node_modules' \
        --exclude='.claude-plugin' \
        --exclude='.cursor-plugin' \
        "$src/" "$dest/"
    else
      # Fallback: copy files over existing directory
      # Use a temp staging dir to strip unwanted content before copying
      staging="$(mktemp -d "$TMPDIR_BASE/vendor-stage-XXXXXX")"
      cp -a "$src/." "$staging/"
      rm -rf "$staging/.git" "$staging/node_modules" \
             "$staging/.claude-plugin" "$staging/.cursor-plugin"
      cp -a "$staging/." "$dest/"
      rm -rf "$staging"
    fi
    echo "  fetch $LOCAL_NAME"
  fi

  fetched=$((fetched + 1))
done

# ── Cleanup temp clones ───────────────────────────────────────────────────

for clone_dir in "${CLONE_CACHE[@]}"; do
  rm -rf "$clone_dir"
done

echo ""
echo "Done. Fetched $fetched vendor skill entries into $SCRIPT_DIR/"
echo "Run install.sh to deploy them to agent config directories."
