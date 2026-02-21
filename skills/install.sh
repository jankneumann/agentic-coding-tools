#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./install.sh [--target <directory>] [--agents <list>] [--mode <symlink|rsync|copy>] [--deps <none|print|apply>] [--python-tools <none|print|apply>] [--copy] [--force]

Install skills into agent config directories using symlinks or synced copies.
Any directory under skills/ with SKILL.md is installed automatically.

Options:
  --target <directory>   Base directory that contains .claude/.codex/.gemini
                         (default: repository root)
  --agents <list>        Comma-separated list of agents to install for.
                         Supported: claude,codex,gemini (default: all)
  --mode <type>          Install mode: symlink, rsync, or copy (default: rsync)
  --deps <mode>          Per-skill dependency hooks mode:
                         none (skip), print (show install commands), apply (execute)
                         Default: print
  --python-tools <mode>  Python tool bootstrap mode for pytest,mypy,ruff:
                         none (skip), print (show commands), apply (install into venv)
                         Default: print
  --python-packages <list>
                         Comma-separated Python packages for --python-tools
                         (default: pytest,mypy,ruff)
  --python-venv <path>   Venv path for --python-tools apply mode.
                         Relative paths are resolved from --target.
                         (default: .skills-venv)
  --copy                 Shorthand for --mode copy
  --force                Replace conflicting existing files/symlinks at destination paths
  -h, --help             Show this help

Examples:
  ./install.sh
  ./install.sh --mode copy --force
  ./install.sh --target "$HOME" --deps none --python-tools none
  ./install.sh --mode symlink
  ./install.sh --target /path/to/project --agents claude,codex --deps apply
USAGE
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="$REPO_ROOT"
AGENTS="claude,codex,gemini"
MODE="rsync"
FORCE=0
DEPS_MODE="print"
PYTHON_TOOLS_MODE="print"
PYTHON_PACKAGES="pytest,mypy,ruff"
PYTHON_VENV=".skills-venv"

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
    --deps)
      [[ $# -ge 2 ]] || { echo "Missing value for --deps" >&2; exit 1; }
      DEPS_MODE="$2"
      shift 2
      ;;
    --python-tools)
      [[ $# -ge 2 ]] || { echo "Missing value for --python-tools" >&2; exit 1; }
      PYTHON_TOOLS_MODE="$2"
      shift 2
      ;;
    --python-packages)
      [[ $# -ge 2 ]] || { echo "Missing value for --python-packages" >&2; exit 1; }
      PYTHON_PACKAGES="$2"
      shift 2
      ;;
    --python-venv)
      [[ $# -ge 2 ]] || { echo "Missing value for --python-venv" >&2; exit 1; }
      PYTHON_VENV="$2"
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

case "$DEPS_MODE" in
  none|print|apply) ;;
  *)
    echo "Invalid --deps: $DEPS_MODE (expected: none, print, or apply)" >&2
    exit 1
    ;;
esac

case "$PYTHON_TOOLS_MODE" in
  none|print|apply) ;;
  *)
    echo "Invalid --python-tools: $PYTHON_TOOLS_MODE (expected: none, print, or apply)" >&2
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

resolve_target_relative_path() {
  local maybe_relative="$1"
  if [[ "$maybe_relative" = /* ]]; then
    printf '%s\n' "$maybe_relative"
  else
    printf '%s/%s\n' "$TARGET_ROOT" "$maybe_relative"
  fi
}

run_skill_dependency_hooks() {
  local mode="$1"
  local hooks_seen=0
  local hooks_failed=0

  if [[ "$mode" == "none" ]]; then
    echo "Skill dependency hooks: skipped (--deps none)"
    return 0
  fi

  printf '\nRunning per-skill dependency hooks (mode=%s)\n' "$mode"
  for skill_path in "${skills[@]}"; do
    local skill_name hook_path
    skill_name="$(basename "$skill_path")"
    hook_path="$skill_path/scripts/install_deps.sh"
    [[ -f "$hook_path" ]] || continue

    hooks_seen=$((hooks_seen + 1))
    if [[ "$mode" == "apply" ]]; then
      echo "  deps  $skill_name (apply)"
      if ! bash "$hook_path" --apply; then
        echo "  warn  $skill_name dependency hook failed" >&2
        hooks_failed=$((hooks_failed + 1))
      fi
    else
      echo "  deps  $skill_name (print)"
      if ! bash "$hook_path"; then
        echo "  warn  $skill_name dependency hook failed" >&2
        hooks_failed=$((hooks_failed + 1))
      fi
    fi
  done

  if [[ $hooks_seen -eq 0 ]]; then
    echo "No per-skill dependency hooks found (expected at <skill>/scripts/install_deps.sh)."
    return 0
  fi

  if [[ $hooks_failed -gt 0 ]]; then
    echo "Dependency hook failures: $hooks_failed" >&2
    return 1
  fi

  echo "Dependency hooks completed: $hooks_seen"
}

install_python_tools() {
  local mode="$1"
  local packages_csv="$2"
  local venv_path="$3"

  if [[ "$mode" == "none" ]]; then
    echo "Python tools bootstrap: skipped (--python-tools none)"
    return 0
  fi

  local -a packages=()
  local -a raw
  local pkg
  IFS=',' read -r -a raw <<< "$packages_csv"
  for pkg in "${raw[@]}"; do
    pkg="${pkg//[[:space:]]/}"
    [[ -n "$pkg" ]] && packages+=("$pkg")
  done

  if [[ ${#packages[@]} -eq 0 ]]; then
    echo "Python tools bootstrap skipped: no packages specified."
    return 0
  fi

  local -a missing=()
  local tool
  for tool in pytest mypy ruff; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      missing+=("$tool")
    fi
  done

  if [[ ${#missing[@]} -eq 0 ]]; then
    echo "Python tools already available in PATH: pytest, mypy, ruff"
    return 0
  fi

  if [[ "$mode" == "print" ]]; then
    local joined_packages
    joined_packages="$(IFS=' '; echo "${packages[*]}")"
    printf '\nPython tools missing from PATH: %s\n' "$(IFS=', '; echo "${missing[*]}")"
    echo "Run the following to install repo-local tooling:"
    echo "  python3 -m venv \"$venv_path\""
    echo "  \"$venv_path/bin/python\" -m pip install --upgrade pip"
    echo "  \"$venv_path/bin/pip\" install $joined_packages"
    return 0
  fi

  local python_cmd
  if command -v python3 >/dev/null 2>&1; then
    python_cmd="python3"
  elif command -v python >/dev/null 2>&1; then
    python_cmd="python"
  else
    echo "python3/python not found; cannot install Python tools." >&2
    return 1
  fi

  printf '\nInstalling repo-local Python tooling into %s\n' "$venv_path"
  "$python_cmd" -m venv "$venv_path"
  "$venv_path/bin/python" -m pip install --upgrade pip
  "$venv_path/bin/pip" install "${packages[@]}"
  echo "Installed tools. Add to PATH when needed:"
  echo "  export PATH=\"$venv_path/bin:\$PATH\""
}

echo "Installing ${#skills[@]} skill directorie(s) from: $SCRIPT_DIR"
echo "Target root: $TARGET_ROOT"
echo "Mode: $MODE"
echo "Dependency hooks: $DEPS_MODE"
echo "Python tools: $PYTHON_TOOLS_MODE"

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

python_venv_path="$(resolve_target_relative_path "$PYTHON_VENV")"
run_skill_dependency_hooks "$DEPS_MODE"
install_python_tools "$PYTHON_TOOLS_MODE" "$PYTHON_PACKAGES" "$python_venv_path"

if [[ "$MODE" == "symlink" ]]; then
  printf '\nDone. Created %d symlink(s), skipped %d.\n' "$total_installed" "$total_skipped"
elif [[ "$MODE" == "copy" ]]; then
  printf '\nDone. Copied %d skill directorie(s), skipped %d.\n' "$total_installed" "$total_skipped"
else
  printf '\nDone. Synced %d skill directorie(s), skipped %d.\n' "$total_installed" "$total_skipped"
fi
