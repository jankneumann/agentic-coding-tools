---
name: performance-optimization
description: |
  Optimizes application performance with the MEASURE → IDENTIFY → FIX →
  VERIFY → GUARD workflow. Covers frontend Core Web Vitals (LCP ≤ 2.5s,
  INP ≤ 200ms, CLS ≤ 0.1), bundle budgets, and React re-render hygiene,
  PLUS backend latency budgets, Postgres/MySQL EXPLAIN ANALYZE workflows,
  N+1 query detection, connection-pool sizing, and async profiling with
  py-spy / cProfile. Use when performance requirements exist, when Core
  Web Vitals or p95 latency miss thresholds, or when profiling reveals
  bottlenecks that need fixing.
category: Performance
tags: [performance, web-vitals, lcp, inp, cls, profiling, n+1, postgres, mysql, py-spy, cprofile, react]
triggers:
  - "performance"
  - "optimize"
  - "slow endpoint"
  - "Core Web Vitals"
  - "LCP"
  - "INP"
  - "CLS"
  - "p95 latency"
  - "EXPLAIN ANALYZE"
  - "N+1 query"
  - "connection pool"
  - "py-spy"
  - "bundle size"
user_invocable: true
related:
  - tech-debt-analysis
  - bug-scrub
---

# Performance Optimization

## Overview

Measure before optimizing. Performance work without measurement is guessing — and guessing leads to premature optimization that adds complexity without improving what matters. Profile first, identify the actual bottleneck, fix it, measure again. Optimize only what measurements prove matters.

## When to Use

- Performance requirements exist in the spec (load-time budgets, response-time SLAs)
- Users or monitoring report slow behavior
- Core Web Vitals scores are below thresholds
- p95 latency on an endpoint exceeds its budget
- You suspect a recent change introduced a regression
- Building features that handle large datasets or high traffic

**When NOT to use:** Don't optimize before you have evidence of a problem. Premature optimization adds complexity that costs more than the performance it gains.

## The Optimization Workflow

```
1. MEASURE  → Establish baseline with real data (synthetic + RUM, or APM + DB log)
2. IDENTIFY → Find the actual bottleneck (not the assumed one)
3. FIX      → Address the specific bottleneck; one variable at a time
4. VERIFY   → Measure again; confirm the improvement is real and worth the cost
5. GUARD    → Add monitoring or a regression test so it stays fixed
```

Skipping any step turns the work into theater. **GUARD** is the most commonly skipped step and the reason regressions reappear within a quarter.

## Frontend: Core Web Vitals Targets

| Metric | Good | Needs Improvement | Poor |
|---|---|---|---|
| **LCP** (Largest Contentful Paint) | ≤ 2.5s | ≤ 4.0s | > 4.0s |
| **INP** (Interaction to Next Paint) | ≤ 200ms | ≤ 500ms | > 500ms |
| **CLS** (Cumulative Layout Shift) | ≤ 0.1 | ≤ 0.25 | > 0.25 |

For the deeper frontend AND backend checklist (TTFB, bundle budgets, image formats, font strategy, pool sizing), see `references/performance-checklist.md`.

## Backend: Latency Budgets

Set p95 budgets per endpoint based on criticality. Echo `references/performance-checklist.md`:

| Endpoint criticality | p50 | p95 | p99 |
|---|---|---|---|
| **Critical user-path** (login, checkout, primary read) | ≤ 100ms | ≤ 300ms | ≤ 1s |
| **Standard read** | ≤ 200ms | ≤ 500ms | ≤ 1.5s |
| **Standard write** | ≤ 300ms | ≤ 800ms | ≤ 2s |
| **Background / batch** | ≤ 1s | ≤ 5s | ≤ 30s |

Budgets without alerts are wishes. Alert at 80% of the budget so you find regressions before users do.

## Step 1 — Measure

### Frontend

Two complementary approaches; use both:

- **Synthetic** (Lighthouse, DevTools Performance tab): controlled conditions, reproducible. Best for CI regression detection and isolating specific issues.
- **RUM** (`web-vitals` library, CrUX): real users in real conditions. Required to validate that a fix actually improved user experience.

```typescript
import { onLCP, onINP, onCLS } from 'web-vitals';

onLCP(({ value }) => sendToAnalytics('lcp', value));
onINP(({ value }) => sendToAnalytics('inp', value));
onCLS(({ value }) => sendToAnalytics('cls', value));
```

### Backend

- Application Performance Monitoring (APM) with per-endpoint p50/p95/p99
- Database query log with timing and `auto_explain` for slow queries
- Distributed tracing across services (OpenTelemetry)

```typescript
console.time('db-query');
const result = await db.query(/* ... */);
console.timeEnd('db-query');
```

### `EXPLAIN ANALYZE` workflow

**Postgres:**

```sql
-- Use BUFFERS to see cache vs disk reads, ANALYZE to actually execute
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT t.id, t.title, u.name AS owner_name
FROM tasks t
JOIN users u ON u.id = t.owner_id
WHERE t.status = 'in_progress'
ORDER BY t.created_at DESC
LIMIT 20;
```

What to look for:

- **`Seq Scan` on a large table** with a `WHERE` clause → missing index.
- **`Rows Removed by Filter` >> rows returned** → the index isn't selective enough; consider a partial or composite index.
- **`Buffers: shared read=N`** with high N → cold cache; benchmark twice (warm vs cold).
- **`-> Sort` with `Sort Method: external merge`** → the sort spilled to disk; raise `work_mem` or add an index that returns rows pre-sorted.

**MySQL:**

```sql
EXPLAIN FORMAT=JSON
SELECT t.id, t.title, u.name AS owner_name
FROM tasks t JOIN users u ON u.id = t.owner_id
WHERE t.status = 'in_progress'
ORDER BY t.created_at DESC
LIMIT 20;
```

The JSON output exposes `cost_info`, `used_key`, `rows_examined_per_scan`, and `attached_condition`. A `type: ALL` access type is the equivalent of Postgres's `Seq Scan`.

## Step 2 — Identify the Bottleneck

Use the symptom to decide what to measure first.

```
What is slow?
├── First page load
│   ├── Large bundle? ──────► Measure bundle size, check code splitting
│   ├── Slow server response? ─► Measure TTFB in DevTools Network waterfall
│   │   ├── DNS long? ──────► dns-prefetch / preconnect
│   │   ├── TCP/TLS long? ──► HTTP/2, edge deployment, keep-alive
│   │   └── Waiting (server) long? ─► Profile backend, check queries and caching
│   └── Render-blocking resources? ─► Check waterfall for CSS/JS blocking
├── Interaction feels sluggish
│   ├── UI freezes on click? ─► Profile main thread; long tasks (>50ms)
│   ├── Form input lag? ────► Check re-renders, controlled-component overhead
│   └── Animation jank? ────► Check layout thrashing, forced reflows
├── Page after navigation
│   ├── Data loading? ──────► API response times, request waterfalls
│   └── Client rendering? ──► Component render time, N+1 fetches
└── Backend / API
    ├── Single endpoint slow? ─► Profile DB queries, check indexes
    ├── All endpoints slow? ──► Connection pool, memory, CPU
    └── Intermittent slowness?─► Lock contention, GC pauses, external deps
```

### Common bottlenecks by category

**Frontend:**

| Symptom | Likely Cause | Investigation |
|---|---|---|
| Slow LCP | Large images, render-blocking resources, slow server | Check network waterfall, image sizes |
| High CLS | Images without dimensions, late-loading content, font shifts | Check layout-shift attribution in DevTools |
| Poor INP | Heavy JavaScript on main thread, large DOM updates | Check long tasks in Performance trace |
| Slow initial load | Large bundle, many network requests | Check bundle size, code splitting |

**Backend:**

| Symptom | Likely Cause | Investigation |
|---|---|---|
| Slow API responses | N+1 queries, missing indexes, unoptimized SQL | Database query log + `EXPLAIN ANALYZE` |
| Memory growth | Leaked references, unbounded caches, large payloads | Heap snapshot / `tracemalloc` |
| CPU spikes | Synchronous heavy computation, regex backtracking, JSON serialization of huge objects | `py-spy top` / `cProfile` |
| High latency under load | Connection-pool exhaustion, GIL contention, thread starvation | APM saturation metrics, `py-spy dump` |
| Intermittent slowness | Lock contention, GC pauses, slow external deps | Tracing across calls; histogram, not just average |

## Step 3 — Fix Common Anti-Patterns

### N+1 Queries (the single most common backend bug)

**TypeScript / Prisma:**

```typescript
// BAD: N+1 — one query per task for the owner
const tasks = await db.tasks.findMany();
for (const task of tasks) {
  task.owner = await db.users.findUnique({ where: { id: task.ownerId } });
}

// GOOD: Single query with join/include
const tasks = await db.tasks.findMany({ include: { owner: true } });
```

**Python / SQLAlchemy:**

```python
# BAD: N+1 — accessing task.owner triggers a per-row SELECT
tasks = session.execute(select(Task)).scalars().all()
for task in tasks:
    print(task.owner.name)  # one SELECT per task

# GOOD: eager-load with joinedload
from sqlalchemy.orm import joinedload
tasks = (
    session.execute(select(Task).options(joinedload(Task.owner)))
    .scalars()
    .unique()
    .all()
)
```

**Three patterns for fixing N+1, in order of preference:**

1. **`SELECT ... IN (...)` batch** — when you have a list of foreign keys and want one extra query that fetches them all:

   ```sql
   SELECT * FROM users WHERE id IN (1, 2, 3, 4, 5);
   ```

2. **JOIN** — when you want a single round trip and the cardinality blow-up is acceptable (one-to-one or one-to-few):

   ```sql
   SELECT t.*, u.name AS owner_name
   FROM tasks t JOIN users u ON u.id = t.owner_id;
   ```

3. **DataLoader / batch-load pattern** — when fetching is interleaved with rendering (GraphQL resolvers, async workflows). Coalesce all `getUser(id)` calls in one tick into a single `getUsers([ids])` call.

### Missing or wrong indexes

```sql
-- Run EXPLAIN ANALYZE; if you see Seq Scan + WHERE on `status`:
CREATE INDEX CONCURRENTLY idx_tasks_status_created_at
  ON tasks (status, created_at DESC);
-- Composite order matters: equality column first, then sort/range column.
```

`CONCURRENTLY` lets the index build without locking writes; use it on production-sized tables.

### Connection-pool sizing

A pool too small queues requests; too large overloads the database. The classic formula:

```
pool_size = ((core_count * 2) + effective_spindle_count)
```

For Postgres on modern SSDs, `effective_spindle_count = 0..1`. So a 4-core app server typically wants `pool_size ≈ 8-10`. Multiply by *application instances* and verify the total stays under the database's `max_connections` minus headroom for admin sessions and background jobs.

In Python with SQLAlchemy:

```python
from sqlalchemy import create_engine

engine = create_engine(
    DATABASE_URL,
    pool_size=10,         # steady-state connections
    max_overflow=5,       # burst capacity
    pool_timeout=3,       # fail fast under saturation, don't queue forever
    pool_pre_ping=True,   # detect dead connections after network blips
)
```

### Async profiling (Python)

**`py-spy` — sampling profiler, no code changes, attaches to a running process:**

```bash
# Live top, like `top` but for Python frames
py-spy top --pid <PID>

# Record a flame graph for 30 seconds
py-spy record -o profile.svg --pid <PID> --duration 30

# One-shot dump of every thread's current stack — great for "stuck" processes
py-spy dump --pid <PID>
```

**`cProfile` — deterministic profiler, in-process:**

```python
import cProfile, pstats

with cProfile.Profile() as prof:
    run_workload()
stats = pstats.Stats(prof).sort_stats("cumulative")
stats.print_stats(30)
```

**`asyncio.gather` for batching independent awaits:**

```python
# BAD: serial — total latency = sum of all calls
user = await fetch_user(uid)
prefs = await fetch_prefs(uid)
flags = await fetch_flags(uid)

# GOOD: parallel — total latency = max of all calls
user, prefs, flags = await asyncio.gather(
    fetch_user(uid),
    fetch_prefs(uid),
    fetch_flags(uid),
)
```

`asyncio.gather` is the async equivalent of fixing N+1 at the HTTP-call layer: replace serial round trips with one concurrent batch.

### Unbounded data fetching

```python
# BAD: pulls every row into memory
tasks = session.execute(select(Task)).scalars().all()

# GOOD: paginate (server-side LIMIT)
tasks = (
    session.execute(
        select(Task).order_by(Task.created_at.desc()).limit(20).offset((page - 1) * 20)
    )
    .scalars()
    .all()
)
```

For very large datasets, prefer **cursor pagination** (`WHERE created_at < :cursor LIMIT 20`) over `OFFSET` — `OFFSET 100000` makes Postgres scan and discard 100k rows.

### Image optimization (frontend LCP fix)

```html
<!-- Hero / LCP image: art direction + resolution switching, high priority -->
<picture>
  <source
    media="(max-width: 767px)"
    srcset="/hero-mobile-400.avif 400w, /hero-mobile-800.avif 800w"
    sizes="100vw"
    width="800" height="1000"
    type="image/avif"
  />
  <source
    srcset="/hero-800.avif 800w, /hero-1200.avif 1200w, /hero-1600.avif 1600w"
    sizes="(max-width: 1200px) 100vw, 1200px"
    width="1200" height="600"
    type="image/avif"
  />
  <img
    src="/hero-desktop.jpg"
    width="1200" height="600"
    fetchpriority="high"
    alt="Hero image description"
  />
</picture>

<!-- Below-the-fold: lazy + async decoding -->
<img
  src="/content.webp"
  width="800" height="400"
  loading="lazy" decoding="async"
  alt="Content image description"
/>
```

### Unnecessary re-renders (React)

```tsx
// BAD: new object identity every render — children re-render
function TaskList() {
  return <TaskFilters options={{ sortBy: 'date', order: 'desc' }} />;
}

// GOOD: stable reference
const DEFAULT_OPTIONS = { sortBy: 'date', order: 'desc' } as const;
function TaskList() {
  return <TaskFilters options={DEFAULT_OPTIONS} />;
}

// React.memo for expensive children that get the same props
const TaskItem = React.memo(function TaskItem({ task }: Props) {
  return <div>{/* expensive render */}</div>;
});

// useMemo for expensive derived computations
function TaskStats({ tasks }: Props) {
  const stats = useMemo(() => calculateStats(tasks), [tasks]);
  return <div>{stats.completed} / {stats.total}</div>;
}
```

Don't sprinkle `React.memo` and `useMemo` everywhere — that's its own bug source. Profile first; memoize only on hot paths the profiler points at.

### Bundle splitting

```typescript
// Modern bundlers (Vite, webpack 5+) tree-shake named imports automatically
// when the dependency ships ESM and is marked sideEffects: false. Profile
// before changing import styles — the real gains come from splitting.

const ChartLibrary = lazy(() => import('./ChartLibrary'));
const SettingsPage = lazy(() => import('./pages/Settings'));

function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <SettingsPage />
    </Suspense>
  );
}
```

### Caching

```typescript
// In-memory cache with TTL for frequently-read, rarely-changed data
const CACHE_TTL = 5 * 60 * 1000;
let cachedConfig: AppConfig | null = null;
let cacheExpiry = 0;

async function getAppConfig(): Promise<AppConfig> {
  if (cachedConfig && Date.now() < cacheExpiry) return cachedConfig;
  cachedConfig = await db.config.findFirst();
  cacheExpiry = Date.now() + CACHE_TTL;
  return cachedConfig;
}

// HTTP caching headers for static assets
app.use(
  '/static',
  express.static('public', {
    maxAge: '1y',
    immutable: true, // requires content-hashed filenames
  })
);
```

## Performance Budget

Set budgets and enforce them in CI:

```
JavaScript bundle: < 200KB gzipped (initial load)
CSS:               < 50KB gzipped
Images:            < 200KB per image (above the fold)
Fonts:             < 100KB total
API response:      < 200ms p95 (critical paths)
Time to Interactive: < 3.5s on 4G
Lighthouse Performance score: ≥ 90
```

```bash
npx bundlesize --config bundlesize.config.json
npx lhci autorun
```

For the full per-category checklist (frontend Core Web Vitals, backend latency, database, caching, monitoring), see `references/performance-checklist.md`.

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "We'll optimize later" | Performance debt compounds: every new feature builds on the slow foundation. Fix obvious anti-patterns now (N+1, missing indexes, unbounded fetches); defer micro-optimizations. |
| "It's fast on my machine" | Your machine isn't the user's. Profile on representative hardware and networks; target p95, not p50. |
| "This optimization is obvious" | If you didn't measure, you don't know. Half of "obvious" optimizations make things slower (e.g. caching cold paths, memoizing trivial renders). |
| "Users won't notice 100ms" | Research shows 100ms delays measurably impact conversion. INP > 200ms is classified "Needs Improvement" by the standard. |
| "The framework handles performance" | Frameworks prevent some issues but can't fix N+1 queries, oversized bundles, missing indexes, or your custom hot path. |
| "I'll just add an index" | Adding indexes blindly slows writes and bloats storage. Run `EXPLAIN ANALYZE` first; index based on actual query plans. |
| "Async means it's parallel" | `await` in a loop is still serial. Use `asyncio.gather` / `Promise.all` for independent calls. |
| "Bigger pool = better throughput" | Beyond the formula, larger pools cause database thrashing and lock contention. Size, alert, and verify under load. |

## Red Flags

- Optimization landed without before/after numbers in the PR description.
- N+1 query patterns in new data-fetching code (look for `for ... await` near a DB call, or ORM lazy-load access in a loop).
- List endpoints without pagination, or pagination params that silently default to "all rows".
- Images without `width`/`height`/`loading`/`decoding` attributes.
- Bundle size grew without a budget check or reviewer comment.
- New endpoint added with no APM dashboard or alert.
- `React.memo` or `useMemo` applied to every component (cargo-cult memoization is its own perf bug).
- Database query plans (`EXPLAIN ANALYZE`) not attached to PRs that change SQL or add indexes.
- `pool_timeout` set to a high value to "hide" pool exhaustion instead of fixing it.
- Synchronous I/O on the event loop in async Python (a `requests.get` inside an `async def`).

## Verification

1. Before- and after-measurements exist with specific numbers (e.g. "p95 dropped from 740ms → 180ms over 1h baseline window").
2. The specific bottleneck was identified and named — not "made it faster" but "removed N+1 in `list_tasks` by switching to `joinedload(Task.owner)`".
3. For frontend changes: Core Web Vitals (LCP, INP, CLS) are within "Good" thresholds in both synthetic and RUM samples.
4. For backend changes: p95 latency for the affected endpoint sits inside its budget, and `EXPLAIN ANALYZE` output is attached for any SQL change.
5. Bundle size delta is reported and within budget; if it grew, the growth is justified by a feature.
6. No N+1 patterns introduced — show one query log line covering the new code path with `count = 1` (or `count = 1 + 1` for a batched fetch).
7. A regression guard is in place: a CI bundle-size check, a Lighthouse-CI run, an APM alert at 80% of budget, or a load test that runs in CI.
8. Existing tests still pass; the optimization didn't change observable behavior.
