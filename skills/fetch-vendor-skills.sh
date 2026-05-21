#!/usr/bin/env bash
set -euo pipefail

# fetch-vendor-skills.sh — Clone external skill repositories and extract
# their skill directories into skills/ so that install.sh auto-discovers them.
#
# Usage:
#   ./fetch-vendor-skills.sh              # Fetch all vendor skills
#   ./fetch-vendor-skills.sh --clean      # Remove vendor skills before fetching
#   ./fetch-vendor-skills.sh --list       # List configured vendor skills
#   ./fetch-vendor-skills.sh --check      # Check for upstream updates (no fetch)
#
# Each vendor entry maps a git repo + source path to a local skill directory name.
# The fetched content is committed alongside our own skills so install.sh works
# without network access. Re-run this script to update from upstream.
#
# After fetching, vendor-manifest.json is updated with the commit SHA and
# timestamp for each repo. Use --check to compare against remote HEAD.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMPDIR_BASE="${TMPDIR:-/tmp}"
CLEAN=0
LIST_ONLY=0
CHECK_ONLY=0
MANIFEST="$SCRIPT_DIR/vendor-manifest.json"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean)  CLEAN=1; shift ;;
    --list)   LIST_ONLY=1; shift ;;
    --check)  CHECK_ONLY=1; shift ;;
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
  "https://github.com/langfuse/skills            | skills/langfuse                                   | langfuse"
  "https://github.com/kepano/obsidian-skills     | skills/obsidian-markdown                          | obsidian-markdown"
  "https://github.com/kepano/obsidian-skills     | skills/obsidian-bases                             | obsidian-bases"
  "https://github.com/kepano/obsidian-skills     | skills/json-canvas                                | json-canvas"
  "https://github.com/kepano/obsidian-skills     | skills/obsidian-cli                               | obsidian-cli"
  "https://github.com/kepano/obsidian-skills     | skills/defuddle                                   | defuddle"
)

# ── Helpers ────────────────────────────────────────────────────────────────
# Avoid bash 4+ associative arrays (macOS ships bash 3.2).
# Use a temp file as a key-value store for clone paths and SHAs.

CLONE_KV="$(mktemp "$TMPDIR_BASE/vendor-clone-kv-XXXXXX")"
trap 'rm -f "$CLONE_KV"' EXIT

# Write "key value" to the KV file
kv_set() { echo "$1 $2" >> "$CLONE_KV"; }

# Read value for key from the KV file (returns empty string if not found)
kv_get() {
  local key="$1"
  # Use awk to find the last entry for the key (in case of duplicates)
  awk -v k="$key" '$1 == k { v = $2 } END { if (v) print v }' "$CLONE_KV"
}

# Check if key exists in the KV file
kv_has() { grep -q "^$1 " "$CLONE_KV" 2>/dev/null; }

parse_entry() {
  local entry="$1"
  REPO_URL="$(echo "$entry" | cut -d'|' -f1 | xargs)"
  SRC_PATH="$(echo "$entry" | cut -d'|' -f2 | xargs)"
  LOCAL_NAME="$(echo "$entry" | cut -d'|' -f3 | xargs)"
}

# Pre-clone all unique repos so we don't clone the same repo multiple times
clone_all_repos() {
  for entry in "${VENDORS[@]}"; do
    parse_entry "$entry"
    if ! kv_has "dir:$REPO_URL"; then
      local clone_dir
      clone_dir="$(mktemp -d "$TMPDIR_BASE/vendor-skill-XXXXXX")"
      echo "  clone  $REPO_URL"
      git clone --depth 1 --quiet "$REPO_URL" "$clone_dir"
      kv_set "dir:$REPO_URL" "$clone_dir"
      kv_set "sha:$REPO_URL" "$(git -C "$clone_dir" rev-parse HEAD)"
    fi
  done
}

# List unique top-level vendor skill directory names
vendor_skill_dirs() {
  local seen_dirs=""
  for entry in "${VENDORS[@]}"; do
    parse_entry "$entry"
    local top_dir="${LOCAL_NAME%%/*}"
    if ! echo "$seen_dirs" | grep -qw "$top_dir" 2>/dev/null; then
      seen_dirs="$seen_dirs $top_dir"
      echo "$top_dir"
    fi
  done
}

# Collect unique repo URLs from the registry
unique_repos() {
  local seen_repos=""
  for entry in "${VENDORS[@]}"; do
    parse_entry "$entry"
    if ! echo "$seen_repos" | grep -qF "$REPO_URL" 2>/dev/null; then
      seen_repos="$seen_repos $REPO_URL"
      echo "$REPO_URL"
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

# ── Check mode ─────────────────────────────────────────────────────────────
# Compare local manifest SHAs against remote HEAD refs (no clone required).

if [[ $CHECK_ONLY -eq 1 ]]; then
  if [[ ! -f "$MANIFEST" ]]; then
    echo "No vendor-manifest.json found. Run without --check first." >&2
    exit 1
  fi

  echo "Checking for upstream updates..."
  updates=0

  for repo_url in $(unique_repos); do
    # Read local SHA from manifest
    local_sha="$(python3 -c "
import json, sys
m = json.load(open(sys.argv[1]))
for v in m.get('vendors', {}).values():
    if v.get('repo') == sys.argv[2]:
        print(v.get('commit', ''))
        sys.exit(0)
print('')
" "$MANIFEST" "$repo_url" 2>/dev/null)"

    # Get remote HEAD without cloning
    remote_sha="$(git ls-remote "$repo_url" HEAD 2>/dev/null | cut -f1)"

    if [[ -z "$local_sha" ]]; then
      printf "  NEW     %-50s (not in manifest)\n" "$repo_url"
      updates=$((updates + 1))
    elif [[ "$local_sha" != "$remote_sha" ]]; then
      printf "  UPDATE  %-50s %s -> %s\n" "$repo_url" "${local_sha:0:8}" "${remote_sha:0:8}"
      updates=$((updates + 1))
    else
      printf "  OK      %-50s %s\n" "$repo_url" "${local_sha:0:8}"
    fi
  done

  if [[ $updates -eq 0 ]]; then
    echo "All vendor skills are up to date."
  else
    echo "$updates vendor repo(s) have updates available. Run without --check to fetch."
  fi
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

  clone_dir="$(kv_get "dir:$REPO_URL")"
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

# ── Write vendor manifest ─────────────────────────────────────────────────
# Records commit SHA and fetch timestamp per repo for --check comparisons.

write_manifest() {
  local today
  today="$(date +%Y-%m-%d)"

  # Build repo→sha pairs as input lines for python3
  local repo_data=""
  for repo_url in $(unique_repos); do
    local sha
    sha="$(kv_get "sha:$repo_url")"
    if [[ -n "$sha" ]]; then
      repo_data="${repo_data}${repo_url} ${sha}"$'\n'
    fi
  done

  # Build paths per repo as python assignments
  local path_assigns=""
  for entry in "${VENDORS[@]}"; do
    parse_entry "$entry"
    path_assigns="${path_assigns}paths.setdefault('${REPO_URL}', []).append('${SRC_PATH}')"$'\n'
  done

  python3 -c "
import json, sys

vendors = {}
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    repo, sha = line.split(' ', 1)
    vendors[repo] = {'commit': sha, 'fetched': '$today'}

paths = {}
$path_assigns

for repo, info in vendors.items():
    info['repo'] = repo
    info['paths'] = paths.get(repo, [])

# Key by org/repo derived from repo URL (always unique, always readable)
result = {}
for repo, info in vendors.items():
    parts = repo.rstrip('/').rsplit('/', 2)
    name = '/'.join(parts[-2:]) if len(parts) >= 2 else parts[-1]
    result[name] = info

json.dump({'vendors': result}, sys.stdout, indent=2)
print()
" > "$MANIFEST" <<< "$repo_data"

  echo "  wrote vendor-manifest.json"
}

write_manifest

# ── Cleanup temp clones ───────────────────────────────────────────────────

for repo_url in $(unique_repos); do
  clone_dir="$(kv_get "dir:$repo_url")"
  if [[ -n "$clone_dir" && -d "$clone_dir" ]]; then
    rm -rf "$clone_dir"
  fi
done

echo ""
echo "Done. Fetched $fetched vendor skill entries into $SCRIPT_DIR/"
echo "Run install.sh to deploy them to agent config directories."
