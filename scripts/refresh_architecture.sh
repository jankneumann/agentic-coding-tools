#!/usr/bin/env bash
# refresh_architecture.sh — Orchestrate the full 3-layer architecture pipeline.
#
# Layer 1: Code Analysis    — Per-language analyzers (parallel)
# Layer 2: Insight Synthesis — Graph compiler + validator + parallel zones
# Layer 3: Report Aggregation — Views + Markdown report
#
# Handles partial failures gracefully: if one analyzer fails, the pipeline
# continues with whatever intermediate outputs are available.
#
# Usage:
#   ./scripts/refresh_architecture.sh            # Full refresh
#   ./scripts/refresh_architecture.sh --quick    # Skip Layer 3 (views/report)
#
# This script is designed to run from the project root directory.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# All paths are relative to CWD and configurable via environment variables.
# When called from the Makefile, these are passed in; when called directly,
# the defaults assume you're running from the project being analyzed.
ARCH_DIR="${ARCH_DIR:-docs/architecture-analysis}"
VIEWS_DIR="${ARCH_DIR}/views"
SCRIPTS_DIR="${SCRIPTS_DIR:-scripts}"
PYTHON_SRC_DIR="${PYTHON_SRC_DIR:-src}"
TS_SRC_DIR="${TS_SRC_DIR:-web}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-supabase/migrations}"

GRAPH_FILE="${ARCH_DIR}/architecture.graph.json"
SUMMARY_FILE="${ARCH_DIR}/architecture.summary.json"
DIAG_FILE="${ARCH_DIR}/architecture.diagnostics.json"
ZONES_FILE="${ARCH_DIR}/parallel_zones.json"
REPORT_FILE="${ARCH_DIR}/architecture.report.md"

PY_ANALYSIS="${ARCH_DIR}/python_analysis.json"
TS_ANALYSIS="${ARCH_DIR}/ts_analysis.json"
PG_ANALYSIS="${ARCH_DIR}/postgres_analysis.json"

PYTHON="${PYTHON:-python3}"
AUTO_INSTALL_DEPS="${AUTO_INSTALL_DEPS:-true}"
SCRIPTS_ABS_DIR="$(cd "${SCRIPTS_DIR}" 2>/dev/null && pwd || true)"
TOOLS_ROOT_DIR="${SCRIPTS_ABS_DIR%/scripts}"

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

# Use simple variables instead of associative arrays (bash 3 compat)
STEPS="python_analyzer postgres_analyzer treesitter_sql typescript_analyzer compiler treesitter_enrichment comment_linker pattern_reporter validator parallel_zones views report"
TREESITTER_ENABLED="${TREESITTER_ENABLED:-true}"
ENRICHMENT_FILE="${ARCH_DIR}/treesitter_enrichment.json"
COMMENT_INSIGHTS_FILE="${ARCH_DIR}/comment_insights.json"
PATTERN_INSIGHTS_FILE="${ARCH_DIR}/pattern_insights.json"
QUERIES_DIR="${SCRIPTS_DIR}/treesitter_queries"
ERRORS=0
WARNINGS=0
START_TIME=$(date +%s)

_set_result() { eval "RESULT_$1=$2"; }
_get_result() { eval "echo \${RESULT_$1:-N/A}"; }
pass()  { _set_result "$1" "PASS"; }
fail()  { _set_result "$1" "FAIL"; ERRORS=$((ERRORS + 1)); }
skip()  { _set_result "$1" "SKIP"; WARNINGS=$((WARNINGS + 1)); }
info()  { echo "[INFO]  $*"; }
warn()  { echo "[WARN]  $*"; WARNINGS=$((WARNINGS + 1)); }
error() { echo "[ERROR] $*"; }

try_install_typescript_deps() {
    if [ "${AUTO_INSTALL_DEPS}" != "true" ]; then
        return 1
    fi
    if ! command -v npm >/dev/null 2>&1; then
        return 1
    fi
    if [ -z "${TOOLS_ROOT_DIR}" ] || [ ! -d "${TOOLS_ROOT_DIR}" ]; then
        return 1
    fi

    info "Attempting to install missing TypeScript analyzer deps (ts-morph, typescript, ts-node)..."
    if (
        cd "${TOOLS_ROOT_DIR}" &&
        npm install --no-save ts-morph typescript ts-node
    ); then
        info "TypeScript analyzer deps installed"
        return 0
    fi
    return 1
}

check_treesitter() {
    # Check if tree-sitter is available via the scripts venv
    if [ "${TREESITTER_ENABLED}" != "true" ]; then
        return 1
    fi
    local scripts_python="${SCRIPTS_DIR}/.venv/bin/python"
    if [ -x "${scripts_python}" ]; then
        if "${scripts_python}" -c "import tree_sitter; import tree_sitter_sql" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

try_install_jsonschema() {
    if [ "${AUTO_INSTALL_DEPS}" != "true" ]; then
        return 1
    fi
    info "Attempting to install missing Python dependency: jsonschema"
    if command -v uv >/dev/null 2>&1; then
        if uv pip install --python "${PYTHON}" jsonschema; then
            info "jsonschema installed via uv"
            return 0
        fi
    fi
    if ${PYTHON} -m pip install jsonschema; then
        info "jsonschema installed via pip"
        return 0
    fi
    return 1
}

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

info "=== Architecture Refresh Pipeline (3-Layer) ==="
info "Project root: $(pwd)"
info "Output dir:   ${ARCH_DIR}"
if [ "$QUICK" = true ]; then
    info "Mode:         --quick (skipping Layer 3: views + report)"
fi
echo ""

mkdir -p "${ARCH_DIR}" "${VIEWS_DIR}"

# ═══════════════════════════════════════════════════════════════════════════
# Layer 1: Code Analysis (per-language analyzers)
# ═══════════════════════════════════════════════════════════════════════════

info "══════════════════════════════════════════════"
info "  Layer 1: Code Analysis"
info "══════════════════════════════════════════════"
echo ""

# ---------------------------------------------------------------------------
# Step 1.1: Python Analyzer
# ---------------------------------------------------------------------------

info "--- [1.1] Python Analyzer ---"
info "Source: ${PYTHON_SRC_DIR}"

if [ ! -d "${PYTHON_SRC_DIR}" ]; then
    error "Python source directory not found: ${PYTHON_SRC_DIR}"
    fail "python_analyzer"
elif [ ! -f "${SCRIPTS_DIR}/analyze_python.py" ]; then
    warn "Python analyzer script not found: ${SCRIPTS_DIR}/analyze_python.py"
    fail "python_analyzer"
else
    if ${PYTHON} "${SCRIPTS_DIR}/analyze_python.py" \
        "${PYTHON_SRC_DIR}" \
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
# Step 1.2: Postgres Analyzer
# ---------------------------------------------------------------------------

info "--- [1.2] Postgres Analyzer ---"
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
# Step 1.2b: Tree-sitter SQL Analyzer (replaces regex parser when available)
# ---------------------------------------------------------------------------

info "--- [1.2b] Tree-sitter SQL Analyzer ---"

if check_treesitter; then
    SCRIPTS_PYTHON="${SCRIPTS_DIR}/.venv/bin/python"
    if [ -f "${SCRIPTS_DIR}/analyze_sql_treesitter.py" ] && [ -d "${MIGRATIONS_DIR}" ]; then
        if "${SCRIPTS_PYTHON}" "${SCRIPTS_DIR}/analyze_sql_treesitter.py" \
            "${MIGRATIONS_DIR}" \
            --output "${PG_ANALYSIS}" 2>&1; then
            info "Tree-sitter SQL analysis overwrote ${PG_ANALYSIS} (enhanced)"
            pass "treesitter_sql"
        else
            warn "Tree-sitter SQL analyzer failed — regex output retained"
            skip "treesitter_sql"
        fi
    else
        skip "treesitter_sql"
    fi
else
    info "Tree-sitter not available — using regex SQL analyzer output"
    skip "treesitter_sql"
fi
echo ""

# ---------------------------------------------------------------------------
# Step 1.3: TypeScript Analyzer (optional)
# ---------------------------------------------------------------------------

info "--- [1.3] TypeScript Analyzer ---"

if [ ! -f "${SCRIPTS_DIR}/analyze_typescript.ts" ]; then
    warn "TypeScript analyzer script not found: ${SCRIPTS_DIR}/analyze_typescript.ts — skipping"
    skip "typescript_analyzer"
elif ! command -v npx >/dev/null 2>&1; then
    warn "npx not found — skipping TypeScript analyzer (install Node.js to enable)"
    skip "typescript_analyzer"
else
    if ! npx ts-morph --version >/dev/null 2>&1 && ! node -e "require('ts-morph')" >/dev/null 2>&1; then
        if ! try_install_typescript_deps || \
           ! npx ts-morph --version >/dev/null 2>&1 && ! node -e "require('ts-morph')" >/dev/null 2>&1; then
            warn "ts-morph not installed — skipping TypeScript analyzer"
            warn "Install with: npm install ts-morph typescript ts-node"
            skip "typescript_analyzer"
        fi
    fi

    if [ "$(_get_result typescript_analyzer)" != "SKIP" ]; then
        if npx ts-node "${SCRIPTS_DIR}/analyze_typescript.ts" \
            "${TS_SRC_DIR}" \
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
# Check for any intermediate outputs
# ---------------------------------------------------------------------------

HAS_INPUT=false
[ -f "${PY_ANALYSIS}" ] && HAS_INPUT=true
[ -f "${PG_ANALYSIS}" ] && HAS_INPUT=true
[ -f "${TS_ANALYSIS}" ] && HAS_INPUT=true

if [ "$HAS_INPUT" = false ]; then
    error "No analyzer outputs available — cannot proceed with Layer 2"
    fail "compiler"
    fail "validator"
    skip "parallel_zones"
    skip "views"
    skip "report"
else

# ═══════════════════════════════════════════════════════════════════════════
# Layer 2: Insight Synthesis
# ═══════════════════════════════════════════════════════════════════════════

info "══════════════════════════════════════════════"
info "  Layer 2: Insight Synthesis"
info "══════════════════════════════════════════════"
echo ""

# ---------------------------------------------------------------------------
# Step 2.1: Graph Compiler (builds graph + links + flow/impact/summary)
# ---------------------------------------------------------------------------

info "--- [2.1] Graph Compiler (6-stage pipeline) ---"

if [ ! -f "${SCRIPTS_DIR}/compile_architecture_graph.py" ]; then
    warn "Compiler script not found: ${SCRIPTS_DIR}/compile_architecture_graph.py"
    fail "compiler"
else
    if ${PYTHON} "${SCRIPTS_DIR}/compile_architecture_graph.py" \
        --input-dir "${ARCH_DIR}" \
        --output-dir "${ARCH_DIR}" 2>&1; then
        info "Graph compiled to ${GRAPH_FILE}"
        info "Summary written to ${SUMMARY_FILE}"
        pass "compiler"
    else
        error "Graph compiler failed (exit code $?)"
        fail "compiler"
    fi
fi
echo ""

# ---------------------------------------------------------------------------
# Step 2.1b: Tree-sitter Enrichment Pass
# ---------------------------------------------------------------------------

info "--- [2.1b] Tree-sitter Enrichment ---"

if check_treesitter && [ -f "${SCRIPTS_DIR}/enrich_with_treesitter.py" ]; then
    SCRIPTS_PYTHON="${SCRIPTS_DIR}/.venv/bin/python"
    ENRICH_ARGS=("--queries" "${QUERIES_DIR}" "--output" "${ENRICHMENT_FILE}")
    [ -d "${PYTHON_SRC_DIR}" ] && ENRICH_ARGS+=("--python-src" "${PYTHON_SRC_DIR}")
    [ -d "${TS_SRC_DIR}" ] && ENRICH_ARGS+=("--ts-src" "${TS_SRC_DIR}")
    [ -f "${GRAPH_FILE}" ] && ENRICH_ARGS+=("--graph" "${GRAPH_FILE}")

    if "${SCRIPTS_PYTHON}" "${SCRIPTS_DIR}/enrich_with_treesitter.py" \
        "${ENRICH_ARGS[@]}" 2>&1; then
        info "Enrichment written to ${ENRICHMENT_FILE}"
        pass "treesitter_enrichment"
    else
        warn "Tree-sitter enrichment failed"
        skip "treesitter_enrichment"
    fi
else
    info "Tree-sitter not available — skipping enrichment"
    skip "treesitter_enrichment"
fi
echo ""

# ---------------------------------------------------------------------------
# Step 2.1c: Comment Linker Insight Module
# ---------------------------------------------------------------------------

info "--- [2.1c] Comment Linker ---"

if [ -f "${ENRICHMENT_FILE}" ] && [ -f "${SCRIPTS_DIR}/insights/comment_linker.py" ]; then
    SCRIPTS_PYTHON="${SCRIPTS_DIR}/.venv/bin/python"
    if "${SCRIPTS_PYTHON}" "${SCRIPTS_DIR}/insights/comment_linker.py" \
        --input-dir "${ARCH_DIR}" \
        --output "${COMMENT_INSIGHTS_FILE}" 2>&1; then
        info "Comment insights written to ${COMMENT_INSIGHTS_FILE}"
        pass "comment_linker"
    else
        warn "Comment linker failed"
        skip "comment_linker"
    fi
else
    skip "comment_linker"
fi
echo ""

# ---------------------------------------------------------------------------
# Step 2.1d: Pattern Reporter Insight Module
# ---------------------------------------------------------------------------

info "--- [2.1d] Pattern Reporter ---"

if [ -f "${ENRICHMENT_FILE}" ] && [ -f "${SCRIPTS_DIR}/insights/pattern_reporter.py" ]; then
    SCRIPTS_PYTHON="${SCRIPTS_DIR}/.venv/bin/python"
    if "${SCRIPTS_PYTHON}" "${SCRIPTS_DIR}/insights/pattern_reporter.py" \
        --input-dir "${ARCH_DIR}" \
        --output "${PATTERN_INSIGHTS_FILE}" 2>&1; then
        info "Pattern insights written to ${PATTERN_INSIGHTS_FILE}"
        pass "pattern_reporter"
    else
        warn "Pattern reporter failed"
        skip "pattern_reporter"
    fi
else
    skip "pattern_reporter"
fi
echo ""

# ---------------------------------------------------------------------------
# Step 2.2: Flow Validator
# ---------------------------------------------------------------------------

info "--- [2.2] Flow Validator ---"

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
    if ! ${PYTHON} -c "import jsonschema" >/dev/null 2>&1; then
        if ! try_install_jsonschema; then
            warn "jsonschema unavailable; schema validation may fail"
        fi
    fi
    if ${PYTHON} "${SCRIPTS_DIR}/validate_schema.py" "${GRAPH_FILE}" 2>&1; then
        info "Schema validation passed"
    else
        warn "Schema validation found issues"
    fi
fi
echo ""

# ---------------------------------------------------------------------------
# Step 2.3: Parallel Zones
# ---------------------------------------------------------------------------

info "--- [2.3] Parallel Zone Analyzer ---"

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
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# Layer 3: Report Aggregation (skipped in --quick mode)
# ═══════════════════════════════════════════════════════════════════════════

if [ "$QUICK" = true ]; then
    info "══════════════════════════════════════════════"
    info "  Layer 3: Report Aggregation (skipped: --quick)"
    info "══════════════════════════════════════════════"
    skip "views"
    skip "report"
else
    info "══════════════════════════════════════════════"
    info "  Layer 3: Report Aggregation"
    info "══════════════════════════════════════════════"
    echo ""

    # -----------------------------------------------------------------------
    # Step 3.1: View Generator (Mermaid diagrams)
    # -----------------------------------------------------------------------

    info "--- [3.1] View Generator ---"

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
    echo ""

    # -----------------------------------------------------------------------
    # Step 3.2: Architecture Report
    # -----------------------------------------------------------------------

    info "--- [3.2] Architecture Report ---"

    if [ ! -f "${GRAPH_FILE}" ]; then
        warn "Graph file not found — skipping report generation"
        skip "report"
    elif [ ! -f "${SCRIPTS_DIR}/reports/architecture_report.py" ]; then
        warn "Report generator not found: ${SCRIPTS_DIR}/reports/architecture_report.py"
        skip "report"
    else
        if ${PYTHON} "${SCRIPTS_DIR}/reports/architecture_report.py" \
            --input-dir "${ARCH_DIR}" \
            --output "${REPORT_FILE}" 2>&1; then
            info "Report written to ${REPORT_FILE}"
            pass "report"
        else
            error "Report generator failed (exit code $?)"
            fail "report"
        fi
    fi
    echo ""
fi

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

for step in $STEPS; do
    result=$(_get_result "$step")
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
    for f in "${GRAPH_FILE}" "${SUMMARY_FILE}" "${DIAG_FILE}" "${ZONES_FILE}" "${REPORT_FILE}" \
             "${PY_ANALYSIS}" "${TS_ANALYSIS}" "${PG_ANALYSIS}" \
             "${ENRICHMENT_FILE}" "${COMMENT_INSIGHTS_FILE}" "${PATTERN_INSIGHTS_FILE}"; do
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
