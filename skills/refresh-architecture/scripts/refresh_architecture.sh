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

# Project input/output paths are relative to CWD and configurable via environment
# variables. Tool paths default to this installed skill, so direct invocation does
# not require the source repository's Makefile or a repo-root scripts directory.
ARCH_DIR="${ARCH_DIR:-docs/architecture-analysis}"
VIEWS_DIR="${ARCH_DIR}/views"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="${SCRIPTS_DIR:-${SCRIPT_DIR}}"
PYTHON_SRC_DIR="${PYTHON_SRC_DIR:-src}"
TS_SRC_DIR="${TS_SRC_DIR:-web}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-database/migrations}"

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

# Optional ORM schema source (D7). Unset — the default — means this whole
# branch is inert and MIGRATIONS_DIR is read exactly as it always was.
#
#   SCHEMA_SOURCE=sqlalchemy   emit CREATE TABLE DDL from a declared MetaData
#                              into a staging directory and point the SQL
#                              analyzers at it. For repositories whose
#                              migrations are Python (Alembic), which have
#                              nothing the SQL analyzers parse.
#   SCHEMA_TARGET              '<module>:<attribute>', e.g. app.models:Base
#   SCHEMA_SOURCE_PYTHON       interpreter that can import the models. Defaults
#                              to PYTHON, but the models usually need the
#                              application's own venv, which is rarely the
#                              analysis interpreter.
#   SCHEMA_SOURCE_DIR          where the DDL is written. Defaults to a
#                              run-scoped temp directory removed on exit, so
#                              nothing unrecorded is promoted into ARCH_DIR;
#                              set it to keep the DDL for inspection.
#
# No database connection is opened by any of this; see dump_sqlalchemy_schema.py.
SCHEMA_SOURCE="${SCHEMA_SOURCE:-}"
SCHEMA_TARGET="${SCHEMA_TARGET:-}"
SCHEMA_SOURCE_PYTHON="${SCHEMA_SOURCE_PYTHON:-${PYTHON}}"
SCHEMA_SOURCE_DIR="${SCHEMA_SOURCE_DIR:-}"
SCHEMA_SOURCE_DIR_IS_TEMP=false
SCRIPTS_ABS_DIR="$(cd "${SCRIPTS_DIR}" 2>/dev/null && pwd || true)"
TOOLS_ROOT_DIR="${SCRIPTS_ABS_DIR%/scripts}"

# Skills root: parent of SCRIPTS_DIR's skill directory (e.g. skills/)
# Used to locate scripts in sibling skill directories (e.g. validate-flows).
SKILLS_ROOT="${SCRIPTS_ABS_DIR%/refresh-architecture/scripts}"

# find_script <filename> — resolve a script path, searching SCRIPTS_DIR first,
# then sibling skill directories under SKILLS_ROOT.
find_script() {
    local name="$1"
    # Direct match in SCRIPTS_DIR
    if [ -f "${SCRIPTS_DIR}/${name}" ]; then
        echo "${SCRIPTS_DIR}/${name}"
        return 0
    fi
    # Search sibling skill script directories
    if [ -d "${SKILLS_ROOT}" ] && [ "${SKILLS_ROOT}" != "${SCRIPTS_ABS_DIR}" ]; then
        local candidate
        candidate="$(find "${SKILLS_ROOT}" -maxdepth 3 -name "${name}" -path "*/scripts/*" -type f 2>/dev/null | head -1)"
        if [ -n "${candidate}" ]; then
            echo "${candidate}"
            return 0
        fi
    fi
    return 1
}

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
# The schema source is a step only where it is configured: an unset
# SCHEMA_SOURCE must not add a row to a summary every existing caller reads.
if [ -n "${SCHEMA_SOURCE}" ]; then
    STEPS="schema_source ${STEPS}"
fi
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

# Interpreter that can run the tree-sitter stages, resolved once and cached,
# together with one verdict per stage. Empty string means "resolved and
# unavailable"; unset means "not yet resolved".
TREESITTER_PYTHON="${TREESITTER_PYTHON:-}"
_TREESITTER_RESOLVED=false

_resolve_treesitter() {
    # Delegates to arch_utils/interpreters.py rather than probing a path here.
    #
    # This used to hard-code "${SCRIPTS_DIR}/.venv/bin/python" — a per-skill venv
    # that does not exist in this repository and that nothing creates — so the
    # probe failed on a normal checkout and three stages skipped silently while
    # provenance, which asked a *different* question in a different process,
    # still recorded tree-sitter as available (issue #378). One resolver means
    # the pipeline and the provenance record cannot disagree.
    #
    # `--shell` emits the same resolution provenance records, as assignments:
    # the interpreter plus TREESITTER_STAGE_<stage>=true|false. Flat variables
    # rather than an associative array, for the bash 3 compatibility this script
    # keeps elsewhere.
    if [ "${_TREESITTER_RESOLVED}" = true ]; then
        return 0
    fi
    _TREESITTER_RESOLVED=true
    TREESITTER_PYTHON=""
    if [ "${TREESITTER_ENABLED}" != "true" ]; then
        return 0
    fi
    local resolved
    resolved="$(${PYTHON} "${SCRIPTS_DIR}/arch_utils/interpreters.py" --shell 2>/dev/null || true)"
    if [ -n "${resolved}" ]; then
        eval "${resolved}"
    fi
    return 0
}

# check_treesitter <stage> — does this stage have every grammar it imports?
#
# Asking per stage instead of once for the pipeline is the point: requiring
# tree_sitter_sql for everything meant one absent grammar disabled the
# enrichment, comment-linker and pattern-reporter stages, which never parse SQL.
check_treesitter() {
    local stage="$1"
    _resolve_treesitter
    if [ -z "${TREESITTER_PYTHON}" ]; then
        return 1
    fi
    local verdict
    verdict="$(eval "echo \${TREESITTER_STAGE_${stage}:-false}")"
    [ "${verdict}" = "true" ]
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
# Step 1.1b: Schema Source (optional; ORM metadata instead of SQL migrations)
# ---------------------------------------------------------------------------
#
# Inert unless SCHEMA_SOURCE is set. When it is, the dumper compiles the
# declared MetaData to CREATE TABLE DDL and MIGRATIONS_DIR is repointed at that
# output for the rest of this run, so the regex and tree-sitter SQL analyzers
# below consume it with no knowledge that it came from an ORM.
#
# A skip leaves MIGRATIONS_DIR exactly as configured rather than substituting
# anything: the SQL analyzers then reach their own D5 verdict about it, which is
# the same answer they would have given had the source never been configured.

if [ -n "${SCHEMA_SOURCE}" ]; then
    info "--- [1.1b] Schema Source (${SCHEMA_SOURCE}) ---"

    if [ "${SCHEMA_SOURCE}" != "sqlalchemy" ]; then
        warn "Unknown SCHEMA_SOURCE: ${SCHEMA_SOURCE} — the only supported value is 'sqlalchemy'"
        warn "Leaving MIGRATIONS_DIR (${MIGRATIONS_DIR}) as configured."
        skip "schema_source"
    elif [ ! -f "${SCRIPTS_DIR}/dump_sqlalchemy_schema.py" ]; then
        warn "Schema dumper not found: ${SCRIPTS_DIR}/dump_sqlalchemy_schema.py — skipping"
        skip "schema_source"
    elif [ -z "${SCHEMA_TARGET}" ]; then
        warn "SCHEMA_SOURCE=sqlalchemy needs SCHEMA_TARGET='<module>:<attribute>'"
        warn "e.g. SCHEMA_TARGET=app.models:Base — skipping the ORM schema source"
        skip "schema_source"
    else
        if [ -z "${SCHEMA_SOURCE_DIR}" ]; then
            SCHEMA_SOURCE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/arch-schema-source.XXXXXX")"
            SCHEMA_SOURCE_DIR_IS_TEMP=true
            # Removed on exit: the DDL is analyzer input, not an artifact, and
            # writing it under ARCH_DIR would promote a file provenance does not
            # record and promotion never deletes.
            trap 'if [ "${SCHEMA_SOURCE_DIR_IS_TEMP}" = true ]; then rm -rf "${SCHEMA_SOURCE_DIR}"; fi' EXIT
        fi
        mkdir -p "${SCHEMA_SOURCE_DIR}"

        # Numbered because analyze_postgres.py orders migrations by a leading
        # integer; the whole schema is one file, so it is the first one.
        SCHEMA_SOURCE_RC=0
        ${SCHEMA_SOURCE_PYTHON} "${SCRIPTS_DIR}/dump_sqlalchemy_schema.py" \
            --target "${SCHEMA_TARGET}" \
            --output "${SCHEMA_SOURCE_DIR}/0001_schema.sql" 2>&1 || SCHEMA_SOURCE_RC=$?

        if [ "${SCHEMA_SOURCE_RC}" -eq 0 ]; then
            MIGRATIONS_DIR="${SCHEMA_SOURCE_DIR}"
            info "SQL analyzers will read the ORM schema at ${MIGRATIONS_DIR}"
            pass "schema_source"
        elif [ "${SCHEMA_SOURCE_RC}" -eq 3 ]; then
            # Inapplicable input, per D5: warn loudly, write nothing, promote.
            # The dumper printed the reason (import error, or a MetaData with no
            # tables) immediately above.
            warn "ORM schema source unusable — see the SKIP reason above"
            warn "MIGRATIONS_DIR (${MIGRATIONS_DIR}) left as configured; the SQL analyzers decide for themselves."
            skip "schema_source"
        else
            error "Schema dumper failed (exit code ${SCHEMA_SOURCE_RC})"
            fail "schema_source"
        fi
    fi
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 1.2: Postgres Analyzer
# ---------------------------------------------------------------------------

info "--- [1.2] Postgres Analyzer ---"
info "Migrations: ${MIGRATIONS_DIR}"

if [ ! -d "${MIGRATIONS_DIR}" ]; then
    # Skip an inapplicable input root; do not fail it.
    #
    # This is the verdict the TypeScript analyzer below already reaches for a
    # missing TS_SRC_DIR, and it is reached here for the same reason: an
    # analyzer with nothing to parse has produced no analysis, and neither an
    # error nor an empty artifact is an honest record of that. `fail` also
    # increments ERRORS, which blocks staged promotion, so a repository whose
    # migrations are Python (Alembic, Django, Prisma) could never write
    # provenance at all — the pipeline failed on every run, permanently.
    warn "MIGRATIONS_DIR does not exist: ${MIGRATIONS_DIR} — skipping Postgres analyzer"
    warn "Set MIGRATIONS_DIR to this repository's SQL migrations root, or leave it unset if there is none."
    warn "NOT writing an empty ${PG_ANALYSIS}: zero tables from a missing directory is a"
    warn "configuration error, and recording it as a result would misreport it as analysis."
    skip "postgres_analyzer"
elif [ ! -f "${SCRIPTS_DIR}/analyze_postgres.py" ]; then
    warn "Postgres analyzer script not found: ${SCRIPTS_DIR}/analyze_postgres.py"
    fail "postgres_analyzer"
elif [ -z "$(find "${MIGRATIONS_DIR}" -type f -name '*.sql' -print -quit 2>/dev/null)" ]; then
    # Present but holding nothing this analyzer parses — the same skip, for the
    # same reason. A present root is not evidence of SQL: it is where a non-SQL
    # migration tool keeps its own chain.
    warn "No *.sql files under ${MIGRATIONS_DIR} — skipping Postgres analyzer"
    warn "The analyzer parses SQL migrations; a repository using a non-SQL migration tool"
    warn "(Alembic, Django, Prisma) keeps nothing here for it to parse."
    warn "Point MIGRATIONS_DIR at a directory of *.sql migrations, or leave it unset if there are none."
    skip "postgres_analyzer"
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

if check_treesitter treesitter_sql; then
    SCRIPTS_PYTHON="${TREESITTER_PYTHON}"
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
    info "Tree-sitter SQL grammar not available — using regex SQL analyzer output"
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
elif [ ! -d "${TS_SRC_DIR}" ]; then
    # Fail loudly on a misconfigured root instead of analysing nothing.
    #
    # The analyzer itself exits 0 on a missing directory and writes an artifact
    # reading "Modules: 0, Components: 0, Functions: 0" — indistinguishable from
    # a repository that genuinely has no TypeScript. That silence is how this
    # repository shipped an all-zeros ts_analysis.json for five months while
    # TS_SRC_DIR pointed at a `web` directory that never existed. A configured
    # input root that is absent is a configuration error, not an empty result.
    warn "TS_SRC_DIR does not exist: ${TS_SRC_DIR} — skipping TypeScript analyzer"
    warn "Set TS_SRC_DIR to this repository's TypeScript root, or leave it unset if there is none."
    warn "NOT writing an empty ${TS_ANALYSIS}: zero modules from a missing directory is a"
    warn "configuration error, and recording it as a result would misreport it as analysis."
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
        # Runner selection, most robust first.
        #
        # Node 23.6+ strips TypeScript types natively, so it runs the analyzer
        # with no transpiler at all. That is preferred because `ts-node` couples
        # the analyzer to whichever `typescript` happens to resolve: this repo
        # has no root package.json, so node_modules is unmanaged, and ts-node
        # 10.9.2 against the resolved typescript 7.x dies in its own config
        # loader with "Cannot read properties of undefined (reading
        # 'fileExists')". Native stripping has no such coupling.
        TS_RUNNER=""
        if node --experimental-strip-types -e '' >/dev/null 2>&1 \
           || node -e 'process.exit(parseInt(process.versions.node,10) >= 23 ? 0 : 1)' >/dev/null 2>&1; then
            TS_RUNNER="node"
        elif npx ts-node --version >/dev/null 2>&1; then
            TS_RUNNER="npx ts-node"
        fi

        if [ -z "${TS_RUNNER}" ]; then
            warn "no usable TypeScript runner (need Node 23.6+ or a working ts-node) — skipping"
            skip "typescript_analyzer"
        elif ${TS_RUNNER} "${SCRIPTS_DIR}/analyze_typescript.ts" \
            "${TS_SRC_DIR}" \
            --output "${TS_ANALYSIS}" 2>&1; then
            info "TypeScript analysis written to ${TS_ANALYSIS} (runner: ${TS_RUNNER})"
            pass "typescript_analyzer"
        else
            error "TypeScript analyzer failed (runner: ${TS_RUNNER}, exit code $?)"
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

if check_treesitter treesitter_enrichment && [ -f "${SCRIPTS_DIR}/enrich_with_treesitter.py" ]; then
    SCRIPTS_PYTHON="${TREESITTER_PYTHON}"
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
    info "Tree-sitter language grammars not available — skipping enrichment"
    skip "treesitter_enrichment"
fi
echo ""

# ---------------------------------------------------------------------------
# Step 2.1c: Comment Linker Insight Module
# ---------------------------------------------------------------------------

info "--- [2.1c] Comment Linker ---"

# check_treesitter is part of the condition, not an assumption. The enrichment
# file can predate this run (in non-staged mode it is whatever the last refresh
# left behind), so its presence does not imply an interpreter was resolved.
if check_treesitter comment_linker && [ -f "${ENRICHMENT_FILE}" ] && [ -f "${SCRIPTS_DIR}/insights/comment_linker.py" ]; then
    SCRIPTS_PYTHON="${TREESITTER_PYTHON}"
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

if check_treesitter pattern_reporter && [ -f "${ENRICHMENT_FILE}" ] && [ -f "${SCRIPTS_DIR}/insights/pattern_reporter.py" ]; then
    SCRIPTS_PYTHON="${TREESITTER_PYTHON}"
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
else
    VALIDATE_FLOWS_SCRIPT="$(find_script validate_flows.py || true)"
    if [ -z "${VALIDATE_FLOWS_SCRIPT}" ]; then
        warn "Validator script not found in ${SCRIPTS_DIR}/ or sibling skills"
        fail "validator"
    elif PYTHONPATH="${SCRIPTS_ABS_DIR}:${PYTHONPATH:-}" ${PYTHON} "${VALIDATE_FLOWS_SCRIPT}" \
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
    SCRIPTS_PYTHON="${TREESITTER_PYTHON:-}"
    if [ -n "${SCRIPTS_PYTHON}" ] && "${SCRIPTS_PYTHON}" -c "import jsonschema" >/dev/null 2>&1; then
        if "${SCRIPTS_PYTHON}" "${SCRIPTS_DIR}/validate_schema.py" "${GRAPH_FILE}" 2>&1; then
            info "Schema validation passed"
        else
            warn "Schema validation found issues"
        fi
    elif ${PYTHON} -c "import jsonschema" >/dev/null 2>&1; then
        if ${PYTHON} "${SCRIPTS_DIR}/validate_schema.py" "${GRAPH_FILE}" 2>&1; then
            info "Schema validation passed"
        else
            warn "Schema validation found issues"
        fi
    else
        warn "jsonschema unavailable; skipping schema validation"
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
