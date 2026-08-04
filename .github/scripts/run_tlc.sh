#!/usr/bin/env bash
#
# Model-check agent-coordinator/formal/coordination.tla with TLC.
#
# This script used to `exit 0` when tla2tools.jar was absent. Nothing in the
# repo ever placed a jar at that path and nothing downloaded one, so the
# formal-coordination job reported success on every run since it was added
# without once invoking TLC. A check that cannot fail is not a check, so the
# missing-jar path is now a hard error and the jar is fetched here.
#
# Env:
#   TLA2TOOLS_JAR      use an existing jar instead of downloading (skips fetch)
#   TLA_TOOLS_VERSION  tlaplus release tag to fetch (default below)
#   TLA_TOOLS_SHA256   expected jar checksum; verified when non-empty
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FORMAL_DIR="${ROOT_DIR}/agent-coordinator/formal"
TLA_TOOLS_VERSION="${TLA_TOOLS_VERSION:-1.8.0}"
TLA_TOOLS_SHA256="${TLA_TOOLS_SHA256:-}"
DEFAULT_JAR="${ROOT_DIR}/.tools/tla2tools.jar"
TLA_JAR="${TLA2TOOLS_JAR:-${DEFAULT_JAR}}"

download_jar() {
  local url="https://github.com/tlaplus/tlaplus/releases/download/v${TLA_TOOLS_VERSION}/tla2tools.jar"
  echo "Fetching tla2tools ${TLA_TOOLS_VERSION} -> ${TLA_JAR}"
  mkdir -p "$(dirname "${TLA_JAR}")"
  if ! curl --fail --silent --show-error --location --retry 3 \
       -o "${TLA_JAR}.tmp" "${url}"; then
    echo "ERROR: could not download ${url}" >&2
    exit 1
  fi
  mv "${TLA_JAR}.tmp" "${TLA_JAR}"
}

if [ ! -f "${TLA_JAR}" ]; then
  if [ -n "${TLA2TOOLS_JAR:-}" ]; then
    # An explicit path that does not exist is a configuration error, not a
    # reason to go fetch something the caller did not ask for.
    echo "ERROR: TLA2TOOLS_JAR=${TLA2TOOLS_JAR} does not exist." >&2
    exit 1
  fi
  download_jar
fi

# Always report the checksum so pinning TLA_TOOLS_SHA256 is a copy-paste, and
# so an unpinned run still records the value it actually used.
ACTUAL_SHA256="$(sha256sum "${TLA_JAR}" | awk '{print $1}')"
echo "tla2tools.jar sha256: ${ACTUAL_SHA256}"

if [ -n "${TLA_TOOLS_SHA256}" ] && [ "${TLA_TOOLS_SHA256}" != "${ACTUAL_SHA256}" ]; then
  echo "ERROR: tla2tools.jar checksum mismatch." >&2
  echo "  expected: ${TLA_TOOLS_SHA256}" >&2
  echo "  actual:   ${ACTUAL_SHA256}" >&2
  exit 1
fi
if [ -z "${TLA_TOOLS_SHA256}" ]; then
  echo "NOTE: TLA_TOOLS_SHA256 is unset, so this download is unverified." \
       "Pin it to the value above in .github/workflows/ci-post-merge.yml."
fi

cd "${FORMAL_DIR}"
echo "Running TLC on coordination.tla (config: coordination.cfg)"
# TLC exits non-zero on an invariant or property violation; `set -e` turns that
# into a job failure, which is the entire point of running it.
java -XX:+UseParallelGC -jar "${TLA_JAR}" \
  -config coordination.cfg \
  -workers auto \
  coordination.tla
