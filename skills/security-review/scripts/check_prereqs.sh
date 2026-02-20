#!/usr/bin/env bash
set -euo pipefail

# Check prerequisite tools for /security-review scanners.
#
# Usage:
#   ./check_prereqs.sh [--json] [--require <comma-separated-items>]
#
# Recognized requirements: java,docker,dependency-check,zap

emit_json=0
require_list=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)
      emit_json=1
      shift
      ;;
    --require)
      [[ $# -ge 2 ]] || { echo "Missing value for --require" >&2; exit 2; }
      require_list="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: ./check_prereqs.sh [--json] [--require <list>]

Options:
  --json            Emit JSON output
  --require <list>  Comma-separated requirement names
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

has_java=0
has_docker=0
has_dependency_check=0
has_docker_access=0
has_zap_via_docker=0

if command -v java >/dev/null 2>&1; then
  has_java=1
fi

if command -v docker >/dev/null 2>&1; then
  has_docker=1
  if docker info >/dev/null 2>&1; then
    has_docker_access=1
    has_zap_via_docker=1
  fi
fi

if command -v dependency-check >/dev/null 2>&1; then
  has_dependency_check=1
fi

missing=()
if [[ -n "$require_list" ]]; then
  IFS=',' read -r -a reqs <<<"$require_list"
  for req in "${reqs[@]}"; do
    req="${req//[[:space:]]/}"
    case "$req" in
      java)
        [[ $has_java -eq 1 ]] || missing+=("java")
        ;;
      docker)
        [[ $has_docker_access -eq 1 ]] || missing+=("docker")
        ;;
      dependency-check)
        if [[ $has_dependency_check -eq 0 && $has_docker_access -eq 0 ]]; then
          missing+=("dependency-check")
        fi
        ;;
      zap)
        [[ $has_zap_via_docker -eq 1 ]] || missing+=("zap")
        ;;
      "")
        ;;
      *)
        missing+=("unknown:$req")
        ;;
    esac
  done
fi

if [[ $emit_json -eq 1 ]]; then
  printf '{'
  printf '"java":%s,' "$([[ $has_java -eq 1 ]] && echo true || echo false)"
  printf '"docker":%s,' "$([[ $has_docker -eq 1 ]] && echo true || echo false)"
  printf '"docker_access":%s,' "$([[ $has_docker_access -eq 1 ]] && echo true || echo false)"
  printf '"dependency_check":%s,' "$([[ $has_dependency_check -eq 1 ]] && echo true || echo false)"
  printf '"zap_via_docker":%s,' "$([[ $has_zap_via_docker -eq 1 ]] && echo true || echo false)"
  printf '"missing":['
  for i in "${!missing[@]}"; do
    [[ $i -gt 0 ]] && printf ','
    printf '"%s"' "${missing[$i]}"
  done
  printf ']}'
  printf '\n'
else
  echo "java=$has_java"
  echo "docker=$has_docker"
  echo "docker_access=$has_docker_access"
  echo "dependency_check=$has_dependency_check"
  echo "zap_via_docker=$has_zap_via_docker"
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "missing=${missing[*]}"
  fi
fi

if [[ ${#missing[@]} -gt 0 ]]; then
  exit 3
fi
