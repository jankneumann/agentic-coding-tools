#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./install.sh [--target <directory>] [--agents <list>] [--force]

Create symlinks for all skills in this repository under agent config directories.

Options:
  --target <directory>   Base directory that contains .claude/.codex/.gemini
                         (default: $HOME)
  --agents <list>        Comma-separated list of agents to install for.
                         Supported: claude,codex,gemini (default: all)
  --force                Replace existing files/directories at destination paths
  -h, --help             Show this help

Examples:
  ./install.sh
  ./install.sh --target "$HOME"
  ./install.sh --target /path/to/project --agents claude,codex
USAGE
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_ROOT="${HOME}"
AGENTS="claude,codex,gemini"
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || { echo "Missing value for --target" >&2; exit 1; }
      TARGET_ROOT="$2"
      shift 2
      ;;
    --agents)
      [[ $# -ge 2 ]] || { echo "Missing value for --agents" >&2; exit 1; }
      AGENTS="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

mkdir -p "$TARGET_ROOT"

IFS=',' read -r -a agent_list <<< "$AGENTS"

agent_dir_for() {
  case "$1" in
    claude) echo ".claude/skills" ;;
    codex)  echo ".codex/skills" ;;
    gemini) echo ".gemini/skills" ;;
    *) return 1 ;;
  esac
}

skills=()
while IFS= read -r entry; do
  name="$(basename "$entry")"
  [[ "$name" == "openspec" ]] && continue

  if [[ -f "$entry/SKILL.md" ]]; then
    skills+=("$entry")
  fi
done < <(find "$SCRIPT_DIR" -mindepth 1 -maxdepth 1 -type d -o -type l | sort)

if [[ ${#skills[@]} -eq 0 ]]; then
  echo "No skills found in $SCRIPT_DIR" >&2
  exit 1
fi

echo "Installing ${#skills[@]} skill link(s) from: $SCRIPT_DIR"
echo "Target root: $TARGET_ROOT"

total_created=0
total_skipped=0

for agent in "${agent_list[@]}"; do
  agent="${agent//[[:space:]]/}"
  [[ -n "$agent" ]] || continue

  if ! rel_dir="$(agent_dir_for "$agent")"; then
    echo "Skipping unsupported agent: $agent" >&2
    continue
  fi

  dest_dir="$TARGET_ROOT/$rel_dir"
  mkdir -p "$dest_dir"
  printf '\n[%s] -> %s\n' "$agent" "$dest_dir"

  for skill_path in "${skills[@]}"; do
    skill_name="$(basename "$skill_path")"
    dest_path="$dest_dir/$skill_name"

    if [[ -e "$dest_path" || -L "$dest_path" ]]; then
      if [[ $FORCE -eq 1 ]]; then
        rm -rf "$dest_path"
      else
        echo "  skip  $skill_name (destination exists; use --force to replace)"
        total_skipped=$((total_skipped + 1))
        continue
      fi
    fi

    ln -s "$skill_path" "$dest_path"
    echo "  link  $skill_name -> $skill_path"
    total_created=$((total_created + 1))
  done
done

printf '\nDone. Created %d link(s), skipped %d.\n' "$total_created" "$total_skipped"
