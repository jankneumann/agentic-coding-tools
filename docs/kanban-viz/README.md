# Kanban Viz — Developer Guide

A real-time Kanban board for observing coordinator work-queue state.
Connects to the coordinator API over SSE for live updates.

## Quick Start

```bash
cd apps/kanban-viz
npm install
npm run dev          # starts Vite dev server on http://localhost:5173
```

Configure the coordinator URL and API key via environment variables or the
`VITE_COORDINATOR_URL` / `VITE_API_KEY` prefix in a `.env.local` file:

```
VITE_COORDINATOR_URL=http://localhost:8000
VITE_API_KEY=your-api-key-here
```

## Auth

The board uses `Authorization: Bearer <api-key>` for every request (design D11).
The SSE stream uses a short-lived single-use JWT minted by `POST /events/auth`.

## Tauri Scaffold

`apps/kanban-viz/src-tauri/` contains a minimal Tauri 2.x scaffold.
It is **not built in CI** and has not been packaged for production.
To verify it compiles:

```bash
cd apps/kanban-viz/src-tauri
cargo check
```

The Tauri path uses `src/lib/runtime.ts` `isTauri()` to detect the runtime.
Filesystem writes (saved views, audit events) route through the coordinator
endpoint in browser mode and through `@tauri-apps/api/fs` in Tauri mode,
producing identical JSON output on both paths (design D10).

## Running Tests

```bash
cd apps/kanban-viz
npm test          # watch mode
npm test -- --run # single-pass (CI)
npm run typecheck # TypeScript strict check
```

## Coordinator Endpoints Used

| Endpoint | Purpose |
|---|---|
| `GET /sync-points/status` | Sync-point gate banner (polled every 5s) |
| `GET /worktrees/active` | Active worktree projection |
| `POST /events/auth` | Mint short-lived SSE token |
| `GET /events/work` | SSE stream (transition, audit, snapshot events) |
| `POST /issues/list` | Initial board fetch |
| `PATCH /issues/{id}/labels` | Drag-to-Ready sets `pending-approval` label |
| `POST /agents/{id}/kick` | Force-kick a blocked agent (consent-gated) |
| `PUT /kanban-viz/saved-views/{slug}` | Persist a saved view |
| `POST /kanban-viz/audit` | Append a UI audit event |
