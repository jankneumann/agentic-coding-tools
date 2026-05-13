# Performance Checklist

Cited by `performance-optimization`, `code-review-and-quality`, and any skill that ships latency-sensitive code. Covers frontend Core Web Vitals AND backend latency/throughput.

## Frontend (browser)

### Core Web Vitals targets

- [ ] **LCP** (Largest Contentful Paint) ≤ 2.5s on a mid-tier mobile + 4G
- [ ] **INP** (Interaction to Next Paint) ≤ 200ms p75
- [ ] **CLS** (Cumulative Layout Shift) ≤ 0.1
- [ ] **TTFB** (Time to First Byte) ≤ 600ms

Measure with the `web-vitals` library + RUM sampling. Don't trust local Lighthouse runs as the only signal.

### Bundle budget

- [ ] First-load JS ≤ 200 KB gzipped
- [ ] First-load CSS ≤ 50 KB gzipped
- [ ] Code-split routes; lazy-load below-the-fold components
- [ ] Verify with `bundlesize` or framework-native budget tooling in CI

### Rendering

- [ ] Above-the-fold content renders without waiting on JS hydration
- [ ] Images use modern formats (`avif`/`webp`) with `loading="lazy"` for below-fold and `decoding="async"` everywhere
- [ ] Image dimensions specified to prevent CLS
- [ ] No layout-shifting font swaps (`font-display: optional` or self-host with preload)

### React/SPA-specific

- [ ] No expensive computation in render bodies — memoize with `useMemo`/`useCallback` only after measuring re-render cost
- [ ] Lists ≥100 items use virtualization
- [ ] State is colocated as low in the tree as possible — global stores only when truly cross-cutting
- [ ] No nested context providers triggering whole-subtree re-renders

## Backend (server / async / DB)

### Latency budgets

- [ ] Read endpoints p50 ≤ 50ms / p95 ≤ 200ms / p99 ≤ 500ms (adjust per criticality)
- [ ] Write endpoints p95 ≤ 500ms
- [ ] Background jobs have explicit SLA + monitoring
- [ ] Document the budget in the endpoint's docstring or OpenAPI spec

### Database

- [ ] All queries inspected with `EXPLAIN ANALYZE` (Postgres) / `EXPLAIN FORMAT=JSON` (MySQL)
- [ ] Sequential scans on tables >10k rows have a matching index proposal or documented justification
- [ ] N+1 queries identified and fixed (`SELECT IN`, `JOIN`, or batch-load pattern)
- [ ] Result sets paginated server-side; never return unbounded `SELECT *`
- [ ] Migrations on tables >1M rows use chunked backfills, not single transactions
- [ ] `ANALYZE` runs after large data changes so the planner has fresh stats

### Connection management

- [ ] Connection pool sized to `(workers × concurrency) + headroom`, not "as high as possible"
- [ ] Pool exhaustion has explicit error handling — never silent timeout retries
- [ ] Read replicas routed for read-heavy endpoints when stale-by-N-seconds is acceptable

### Caching

- [ ] Cache keys include version/tenant prefix to avoid cross-contamination
- [ ] Cache TTLs match data volatility — no "infinite" caches without explicit invalidation
- [ ] Cache misses don't stampede the origin (use `cache-aside` with single-flight or probabilistic early refresh)
- [ ] HTTP cache headers (`Cache-Control`, `ETag`, `Vary`) set for every public-readable endpoint

### Async / concurrency

- [ ] CPU-bound work runs in a thread/process pool, not the event loop
- [ ] `await` calls in tight loops use `asyncio.gather` or batching, not sequential awaits
- [ ] Background tasks have timeouts (no unbounded `await`)

## Profiling discipline

- [ ] Performance claims backed by a benchmark (`pytest-benchmark`, `wrk`, `vegeta`, Lighthouse CI)
- [ ] Baseline number recorded BEFORE the optimization
- [ ] After number recorded with the same harness on the same hardware
- [ ] Regression test added to prevent silent re-degradation

## Anti-patterns

- [ ] Premature optimization: did you measure before optimizing? If no, stop.
- [ ] Microbenchmarks proving things that don't survive realistic load
- [ ] "Faster" code that's harder to read with no measurable improvement
- [ ] Optimizing the wrong layer (e.g., shaving 5ms off Redis when DB is 200ms)
