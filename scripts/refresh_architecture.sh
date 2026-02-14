#!/usr/bin/env bash
# refresh_architecture.sh — Orchestrate the full architecture analysis pipeline.
#
# Runs per-language analyzers, the graph compiler, the flow validator, and
# the view generator.  Handles partial failures gracefully: if one analyzer
# fails, the pipeline continues with whatever intermediate outputs are
# available, and a summary is printed at the end.
#
# Usage:
#   ./scripts/refresh_architecture.sh            # Full refresh
#   ./scripts/refresh_architecture.sh --quick    # Skip views and parallel zones
#
# This script is designed to run from the project root directory.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ARCH_DIR=".architecture"
VIEWS_DIR="${ARCH_DIR}/views"
SCRIPTS_DIR="scripts"
PYTHON_SRC="agent-coordinator/src"
MIGRATIONS_DIR="agent-coordinator/supabase/migrations"

GRAPH_FILE="${ARCH_DIR}/architecture.graph.json"
SUMMARY_FILE="${ARCH_DIR}/architecture.summary.json"
DIAG_FILE="${ARCH_DIR}/architecture.diagnostics.json"
ZONES_FILE="${ARCH_DIR}/parallel_zones.json"

PY_ANALYSIS="${ARCH_DIR}/python_analysis.json"
TS_ANALYSIS="${ARCH_DIR}/ts_analysis.json"
PG_ANALYSIS="${ARCH_DIR}/postgres_analysis.json"

PYTHON="${PYTHON:-python3}"

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------

QUICK=false
for arg in "$@"; do
    case "$arg" in
        --quick)
            QUICK=true
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--quick]"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# State tracking
# ---------------------------------------------------------------------------

declare -A RESULTS
STEPS=("python_analyzer" "postgres_analyzer" "typescript_analyzer" "compiler" "validator" "views" "parallel_zones")
ERRORS=0
WARNINGS=0
START_TIME=$(date +%s)

pass()  { RESULTS["$1"]="PASS"; }
fail()  { RESULTS["$1"]="FAIL"; ERRORS=$((ERRORS + 1)); }
skip()  { RESULTS["$1"]="SKIP"; WARNINGS=$((WARNINGS + 1)); }
info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*"; WARNINGS=$((WARNINGS + 1)); }
error() { echo "[ERROR] $*"; }

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

info "=== Architecture Refresh Pipeline ==="
info "Project root: $(pwd)"
info "Output dir:   ${ARCH_DIR}"
if [ "$QUICK" = true ]; then
    info "Mode:         --quick (skipping views and parallel zones)"
fi
echo ""

mkdir -p "${ARCH_DIR}" "${VIEWS_DIR}"

# ---------------------------------------------------------------------------
# Step 1: Python Analyzer
# ---------------------------------------------------------------------------

info "--- [1/6] Python Analyzer ---"
info "Source: ${PYTHON_SRC}"

if [ ! -d "${PYTHON_SRC}" ]; then
    error "Python source directory not found: ${PYTHON_SRC}"
    fail "python_analyzer"
elif [ ! -f "${SCRIPTS_DIR}/analyze_python.py" ]; then
    warn "Python analyzer script not found: ${SCRIPTS_DIR}/analyze_python.py"
    fail "python_analyzer"
else
    if ${PYTHON} "${SCRIPTS_DIR}/analyze_python.py" \
        "${PYTHON_SRC}" \
        --output "${PY_ANALYSIS}" 2>&1; then
        info "Python analysis written to ${PY_ANALYSIS}"
        pass "python_analyzer"
    else
        error "Python analyzer failed (exit code $?)"
        fail "python_analyzer"
    fi
fi
echo ""

# ---------------------------------------------------------------------------
# Step 2: Postgres Analyzer
# ---------------------------------------------------------------------------

info "--- [2/6] Postgres Analyzer ---"
info "Migrations: ${MIGRATIONS_DIR}"

if [ ! -d "${MIGRATIONS_DIR}" ]; then
    error "Migrations directory not found: ${MIGRATIONS_DIR}"
    fail "postgres_analyzer"
elif [ ! -f "${SCRIPTS_DIR}/analyze_postgres.py" ]; then
    warn "Postgres analyzer script not found: ${SCRIPTS_DIR}/analyze_postgres.py"
    fail "postgres_analyzer"
else
    if ${PYTHON} "${SCRIPTS_DIR}/analyze_postgres.py" \
        "${MIGRATIONS_DIR}" \
        --output "${PG_ANALYSIS}" 2>&1; then
        info "Postgres analysis written to ${PG_ANALYSIS}"
        pass "postgres_analyzer"
    else
        error "Postgres analyzer failed (exit code $?)"
        fail "postgres_analyzer"
    fi
fi
echo ""

# ---------------------------------------------------------------------------
# Step 3: TypeScript Analyzer (optional — skip with warning if unavailable)
# ---------------------------------------------------------------------------

info "--- [3/6] TypeScript Analyzer ---"

if [ ! -f "${SCRIPTS_DIR}/analyze_typescript.ts" ]; then
    warn "TypeScript analyzer script not found: ${SCRIPTS_DIR}/analyze_typescript.ts — skipping"
    skip "typescript_analyzer"
elif ! command -v npx >/dev/null 2>&1; then
    warn "npx not found — skipping TypeScript analyzer (install Node.js to enable)"
    skip "typescript_analyzer"
else
    # Check if ts-morph is available
    if ! npx ts-morph --version >/dev/null 2>&1 && ! node -e "require('ts-morph')" >/dev/null 2>&1; then
        warn "ts-morph not installed — skipping TypeScript analyzer"
        warn "Install with: npm install ts-morph typescript"
        skip "typescript_analyzer"
    else
        if npx ts-node "${SCRIPTS_DIR}/analyze_typescript.ts" \
            --output "${TS_ANALYSIS}" 2>&1; then
            info "TypeScript analysis written to ${TS_ANALYSIS}"
            pass "typescript_analyzer"
        else
            error "TypeScript analyzer failed (exit code $?)"
            fail "typescript_analyzer"
        fi
    fi
fi
echo ""

# ---------------------------------------------------------------------------
# Determine whether any intermediate outputs are available for the compiler
# ---------------------------------------------------------------------------

HAS_INPUT=false

if [ -f "${PY_ANALYSIS}" ]; then
    HAS_INPUT=true
fi

if [ -f "${PG_ANALYSIS}" ]; then
    HAS_INPUT=true
fi

if [ -f "${TS_ANALYSIS}" ]; then
    HAS_INPUT=true
fi

if [ "$HAS_INPUT" = false ]; then
    error "No analyzer outputs available — cannot proceed with compilation"
    fail "compiler"
    fail "validator"
    skip "views"
    skip "parallel_zones"
    # Jump to summary
else

# ---------------------------------------------------------------------------
# Step 4: Graph Compiler
# ---------------------------------------------------------------------------

info "--- [4/6] Graph Compiler ---"

if [ ! -f "${SCRIPTS_DIR}/compile_architecture_graph.py" ]; then
    warn "Compiler script not found: ${SCRIPTS_DIR}/compile_architecture_graph.py"
    fail "compiler"
else
    if ${PYTHON} "${SCRIPTS_DIR}/compile_architecture_graph.py" \
        --input-dir "${ARCH_DIR}" \
        --output-dir "${ARCH_DIR}" 2>&1; then
        info "Graph compiled to ${GRAPH_FILE}"
        pass "compiler"
    else
        error "Graph compiler failed (exit code $?)"
        fail "compiler"
    fi
fi
echo ""

# ---------------------------------------------------------------------------
# Step 5: Flow Validator
# ---------------------------------------------------------------------------

info "--- [5/6] Flow Validator ---"

if [ ! -f "${GRAPH_FILE}" ]; then
    warn "Graph file not found — skipping validation"
    skip "validator"
elif [ ! -f "${SCRIPTS_DIR}/validate_flows.py" ]; then
    warn "Validator script not found: ${SCRIPTS_DIR}/validate_flows.py"
    fail "validator"
else
    if ${PYTHON} "${SCRIPTS_DIR}/validate_flows.py" \
        --graph "${GRAPH_FILE}" \
        --output "${DIAG_FILE}" 2>&1; then
        info "Diagnostics written to ${DIAG_FILE}"
        pass "validator"
    else
        error "Flow validator failed (exit code $?)"
        fail "validator"
    fi
fi

# Also run the schema validator if available
if [ -f "${GRAPH_FILE}" ] && [ -f "${SCRIPTS_DIR}/validate_schema.py" ]; then
    info "Running schema validation..."
    if ${PYTHON} "${SCRIPTS_DIR}/validate_schema.py" "${GRAPH_FILE}" 2>&1; then
        info "Schema validation passed"
    else
        warn "Schema validation found issues"
    fi
fi
echo ""

# ---------------------------------------------------------------------------
# Step 6: View Generator and Parallel Zones (skipped in --quick mode)
# ---------------------------------------------------------------------------

if [ "$QUICK" = true ]; then
    info "--- [6/6] Views & Parallel Zones (skipped: --quick mode) ---"
    skip "views"
    skip "parallel_zones"
else
    info "--- [6/6] View Generator & Parallel Zones ---"

    # View generator
    if [ ! -f "${GRAPH_FILE}" ]; then
        warn "Graph file not found — skipping view generation"
        skip "views"
    elif [ ! -f "${SCRIPTS_DIR}/generate_views.py" ]; then
        warn "View generator script not found: ${SCRIPTS_DIR}/generate_views.py"
        fail "views"
    else
        if ${PYTHON} "${SCRIPTS_DIR}/generate_views.py" \
            --graph "${GRAPH_FILE}" \
            --output-dir "${VIEWS_DIR}" 2>&1; then
            info "Views generated in ${VIEWS_DIR}/"
            pass "views"
        else
            error "View generator failed (exit code $?)"
            fail "views"
        fi
    fi

    # Parallel zone analyzer
    if [ ! -f "${GRAPH_FILE}" ]; then
        warn "Graph file not found — skipping parallel zone analysis"
        skip "parallel_zones"
    elif [ ! -f "${SCRIPTS_DIR}/parallel_zones.py" ]; then
        warn "Parallel zones script not found: ${SCRIPTS_DIR}/parallel_zones.py"
        fail "parallel_zones"
    else
        if ${PYTHON} "${SCRIPTS_DIR}/parallel_zones.py" \
            --graph "${GRAPH_FILE}" \
            --output "${ZONES_FILE}" 2>&1; then
            info "Parallel zones written to ${ZONES_FILE}"
            pass "parallel_zones"
        else
            error "Parallel zone analyzer failed (exit code $?)"
            fail "parallel_zones"
        fi
    fi
fi
echo ""

fi  # end of HAS_INPUT block

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo "==========================================="
echo "  Architecture Refresh Summary"
echo "==========================================="
echo ""

for step in "${STEPS[@]}"; do
    result="${RESULTS[$step]:-N/A}"
    case "$result" in
        PASS) symbol="\033[32mPASS\033[0m" ;;
        FAIL) symbol="\033[31mFAIL\033[0m" ;;
        SKIP) symbol="\033[33mSKIP\033[0m" ;;
        *)    symbol="\033[90mN/A\033[0m"  ;;
    esac
    printf "  %-24s [${symbol}]\n" "$step"
done

echo ""
echo "  Elapsed:  ${ELAPSED}s"
echo "  Errors:   ${ERRORS}"
echo "  Warnings: ${WARNINGS}"
echo ""

# List generated artifacts
if [ -d "${ARCH_DIR}" ]; then
    echo "Generated artifacts:"
    for f in "${GRAPH_FILE}" "${SUMMARY_FILE}" "${DIAG_FILE}" "${ZONES_FILE}" \
             "${PY_ANALYSIS}" "${TS_ANALYSIS}" "${PG_ANALYSIS}"; do
        if [ -f "$f" ]; then
            size=$(wc -c < "$f" 2>/dev/null || echo "?")
            printf "  %-50s %s bytes\n" "$f" "$size"
        fi
    done
    if [ -d "${VIEWS_DIR}" ] && [ "$(ls -A "${VIEWS_DIR}" 2>/dev/null)" ]; then
        view_count=$(find "${VIEWS_DIR}" -type f | wc -l)
        echo "  ${VIEWS_DIR}/  (${view_count} files)"
    fi
    echo ""
fi

# Exit code: 0 if no errors (warnings and skips are OK), 1 if any step failed
if [ "$ERRORS" -gt 0 ]; then
    echo "Pipeline completed with ${ERRORS} error(s). Some artifacts may be incomplete."
    exit 1
else
    echo "Pipeline completed successfully."
    exit 0
fi
