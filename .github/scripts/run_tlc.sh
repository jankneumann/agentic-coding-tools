#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FORMAL_DIR="${ROOT_DIR}/agent-coordinator/formal"
TLA_JAR="${TLA2TOOLS_JAR:-${ROOT_DIR}/.tools/tla2tools.jar}"

if [ ! -f "${TLA_JAR}" ]; then
  echo "TLA+ tools jar not found: ${TLA_JAR}"
  echo "Set TLA2TOOLS_JAR or place tla2tools.jar at .tools/tla2tools.jar"
  exit 0
fi

cd "${FORMAL_DIR}"
java -jar "${TLA_JAR}" -config coordination.cfg coordination.tla
