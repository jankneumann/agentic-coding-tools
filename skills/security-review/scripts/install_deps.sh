#!/usr/bin/env bash
set -euo pipefail

# Install helper for /security-review prerequisites.
#
# By default this script prints install commands.
# Use --apply to execute them.

apply=0
components="java,docker,dependency-check"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      apply=1
      shift
      ;;
    --components)
      [[ $# -ge 2 ]] || { echo "Missing value for --components" >&2; exit 2; }
      components="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: ./install_deps.sh [--apply] [--components <list>]

Options:
  --apply               Execute install commands (default: print-only)
  --components <list>   Comma-separated subset: java,docker,dependency-check
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

os="unknown"
if [[ "$(uname -s)" == "Darwin" ]]; then
  os="macos"
elif [[ -f /etc/os-release ]]; then
  . /etc/os-release
  os="${ID:-linux}"
fi

have_brew=0
have_apt=0
have_dnf=0

command -v brew >/dev/null 2>&1 && have_brew=1
command -v apt-get >/dev/null 2>&1 && have_apt=1
command -v dnf >/dev/null 2>&1 && have_dnf=1

commands=()

want_component() {
  local needle="$1"
  IFS=',' read -r -a parts <<<"$components"
  for part in "${parts[@]}"; do
    part="${part//[[:space:]]/}"
    [[ "$part" == "$needle" ]] && return 0
  done
  return 1
}

add_command() {
  local cmd="$1"
  commands+=("$cmd")
}

if want_component "java"; then
  if [[ $have_brew -eq 1 ]]; then
    add_command "brew install openjdk@17"
  elif [[ $have_apt -eq 1 ]]; then
    add_command "sudo apt-get update && sudo apt-get install -y openjdk-17-jre"
  elif [[ $have_dnf -eq 1 ]]; then
    add_command "sudo dnf install -y java-17-openjdk"
  fi
fi

if want_component "docker"; then
  if [[ $have_brew -eq 1 ]]; then
    add_command "brew install --cask docker"
  elif [[ $have_apt -eq 1 ]]; then
    add_command "sudo apt-get update && sudo apt-get install -y docker.io && sudo systemctl enable --now docker"
  elif [[ $have_dnf -eq 1 ]]; then
    add_command "sudo dnf install -y docker && sudo systemctl enable --now docker"
  fi
fi

if want_component "dependency-check"; then
  if [[ $have_brew -eq 1 ]]; then
    add_command "brew install dependency-check"
  elif [[ $have_apt -eq 1 ]]; then
    add_command "echo 'Use Docker fallback for dependency-check on apt-based systems or install manually from https://github.com/dependency-check/DependencyCheck/releases'"
  elif [[ $have_dnf -eq 1 ]]; then
    add_command "echo 'Use Docker fallback for dependency-check on dnf-based systems or install manually from https://github.com/dependency-check/DependencyCheck/releases'"
  fi
fi

if [[ ${#commands[@]} -eq 0 ]]; then
  echo "No installer commands available for this platform ($os)."
  echo "See skills/security-review/docs/dependencies.md for manual steps."
  exit 1
fi

echo "Detected platform: $os"
if [[ $apply -eq 0 ]]; then
  echo "Print-only mode. Run with --apply to execute these commands:"
  for cmd in "${commands[@]}"; do
    echo "  $cmd"
  done
  exit 0
fi

failed=0
for cmd in "${commands[@]}"; do
  echo "Running: $cmd"
  if ! eval "$cmd"; then
    echo "Command failed: $cmd" >&2
    failed=1
  fi
done

if [[ $failed -ne 0 ]]; then
  echo "Some install commands failed. See skills/security-review/docs/dependencies.md for manual remediation." >&2
  exit 1
fi

echo "Dependency bootstrap completed."
