#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./install.sh [--target <directory>] [--agents <list>] [--mode <symlink|rsync|copy>] [--copy] [--force]

Install skills into agent config directories using symlinks or synced copies.
Any directory under skills/ with SKILL.md is installed automatically.

Options:
  --target <directory>   Base directory that contains .claude/.codex/.gemini
                         (default: $HOME)
  --agents <list>        Comma-separated list of agents to install for.
                         Supported: claude,codex,gemini (default: all)
  --mode <type>          Install mode: symlink, rsync, or copy (default: rsync)
  --copy                 Shorthand for --mode copy
  --force                Replace conflicting existing files/symlinks at destination paths
  -h, --help             Show this help

Examples:
  ./install.sh
  ./install.sh --mode copy --force
  ./install.sh --target "$HOME"
  ./install.sh --mode symlink
  ./install.sh --target /path/to/project --agents claude,codex
USAGE
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_ROOT="${HOME}"
AGENTS="claude,codex,gemini"
MODE="rsync"
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
    --mode)
      [[ $# -ge 2 ]] || { echo "Missing value for --mode" >&2; exit 1; }
      MODE="$2"
      shift 2
      ;;
    --copy)
      MODE="copy"
      shift
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

case "$MODE" in
  symlink|rsync|copy) ;;
  *)
    echo "Invalid --mode: $MODE (expected: symlink, rsync, or copy)" >&2
    exit 1
    ;;
esac

agent_dir_for() {
  case "$1" in
    claude) echo ".claude/skills" ;;
    codex)  echo ".codex/skills" ;;
    gemini) echo ".gemini/skills" ;;
    *) return 1 ;;
  esac
}

canonicalize_existing_dir() {
  local path="$1"
  (cd "$path" 2>/dev/null && pwd -P)
}

canonicalize_target_path() {
  local path="$1"
  local parent base
  parent="$(dirname "$path")"
  base="$(basename "$path")"
  printf '%s/%s\n' "$(canonicalize_existing_dir "$parent")" "$base"
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

echo "Installing ${#skills[@]} skill directorie(s) from: $SCRIPT_DIR"
echo "Target root: $TARGET_ROOT"
echo "Mode: $MODE"

total_installed=0
total_skipped=0

if [[ "$MODE" == "rsync" || "$MODE" == "copy" ]]; then
  if ! command -v rsync >/dev/null 2>&1; then
    echo "$MODE mode requested but rsync was not found in PATH" >&2
    exit 1
  fi
fi

sync_label="sync"
if [[ "$MODE" == "copy" ]]; then
  sync_label="copy"
fi

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
    src_real="$(canonicalize_existing_dir "$skill_path")"
    dest_real="$(canonicalize_target_path "$dest_path")"

    if [[ "$src_real" == "$dest_real" ]]; then
      echo "  skip  $skill_name (source and destination are the same path)"
      total_skipped=$((total_skipped + 1))
      continue
    fi

    if [[ -d "$dest_path" ]]; then
      dest_existing_real="$(canonicalize_existing_dir "$dest_path")"
      if [[ "$src_real" == "$dest_existing_real" ]]; then
        if [[ "$MODE" != "symlink" && -L "$dest_path" && $FORCE -eq 1 ]]; then
          rm -rf "$dest_path"
        else
          echo "  skip  $skill_name (destination resolves to source path)"
          total_skipped=$((total_skipped + 1))
          continue
        fi
      fi
    fi

    if [[ -e "$dest_path" || -L "$dest_path" ]]; then
      if [[ "$MODE" == "symlink" ]]; then
        if [[ $FORCE -eq 1 ]]; then
          rm -rf "$dest_path"
        else
          echo "  skip  $skill_name (destination exists; use --force to replace)"
          total_skipped=$((total_skipped + 1))
          continue
        fi
      else
        if [[ -L "$dest_path" ]]; then
          if [[ $FORCE -eq 1 ]]; then
            rm -rf "$dest_path"
          else
            echo "  skip  $skill_name (destination is a symlink; use --force to replace with a directory)"
            total_skipped=$((total_skipped + 1))
            continue
          fi
        elif [[ ! -d "$dest_path" ]]; then
          if [[ $FORCE -eq 1 ]]; then
            rm -rf "$dest_path"
          else
            echo "  skip  $skill_name (destination exists and is not a directory; use --force to replace)"
            total_skipped=$((total_skipped + 1))
            continue
          fi
        fi
      fi
    fi

    if [[ "$MODE" == "symlink" ]]; then
      ln -s "$skill_path" "$dest_path"
      echo "  link  $skill_name -> $skill_path"
    else
      mkdir -p "$dest_path"
      rsync -a --delete "$skill_path/" "$dest_path/"
      echo "  $sync_label  $skill_name -> $dest_path"
    fi
    total_installed=$((total_installed + 1))
  done
done

if [[ "$MODE" == "symlink" ]]; then
  printf '\nDone. Created %d symlink(s), skipped %d.\n' "$total_installed" "$total_skipped"
elif [[ "$MODE" == "copy" ]]; then
  printf '\nDone. Copied %d skill directorie(s), skipped %d.\n' "$total_installed" "$total_skipped"
else
  printf '\nDone. Synced %d skill directorie(s), skipped %d.\n' "$total_installed" "$total_skipped"
fi
