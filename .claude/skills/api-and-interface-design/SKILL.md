---
name: api-and-interface-design
description: |
  Guides stable API and interface design for REST endpoints, GraphQL schemas,
  module boundaries, and component contracts. Use when designing new APIs,
  defining type contracts between modules, establishing boundaries between
  frontend and backend, or modifying existing public interfaces. Covers
  Hyrum's Law, contract-first design, the One-Version Rule, REST resource
  patterns, pagination, PATCH semantics, and idiomatic type-system patterns
  in both TypeScript (discriminated unions, branded types) and Python
  (Pydantic discriminated unions, NewType branded types, FastAPI route
  shapes, frozen dataclasses).
category: Engineering
tags: [api, interface, rest, contracts, hyrum, typescript, python, fastapi, pydantic, validation]
triggers:
  - "design an API"
  - "API design"
  - "interface design"
  - "REST endpoint"
  - "contract-first"
  - "module boundary"
  - "Hyrum's Law"
  - "API versioning"
  - "discriminated union"
  - "branded type"
user_invocable: true
related:
  - security-review
---

# API and Interface Design

## Overview

Design stable, well-documented interfaces that are hard to misuse. Good interfaces make the right thing easy and the wrong thing hard. This applies to REST APIs, GraphQL schemas, module boundaries, component props, function signatures, and any surface where one piece of code talks to another.

This skill ships with **TypeScript and Python examples side-by-side**. Pick the one that matches the codebase you are working in; the principles are identical.

## When to Use

- Designing new API endpoints
- Defining module boundaries or contracts between teams
- Creating component prop interfaces or function signatures
- Establishing database schema that informs API shape
- Changing existing public interfaces

## Core Principles

### Hyrum's Law

> With a sufficient number of users of an API, all observable behaviors of your system will be depended on by somebody, regardless of what you promise in the contract.

Every observable behavior — including undocumented quirks, error message text, response ordering, and timing — becomes a de facto contract once users depend on it. Design implications:

- **Be intentional about what you expose.** Every observable behavior is a potential commitment.
- **Don't leak implementation details.** If users can observe it, they will depend on it.
- **Plan for deprecation at design time.** Versioning, sunset headers, and migration paths are part of the original design, not a later cleanup.
- **Tests are not enough.** Even with perfect contract tests, "safe" changes can break real users who depend on undocumented behavior.

### The One-Version Rule

Avoid forcing consumers to choose between multiple versions of the same dependency or API. Diamond dependency problems arise when different consumers need different versions of the same thing. Design for a world where only one version exists at a time — extend rather than fork.

### 1. Contract First

Define the interface before implementing it. The contract is the spec; implementation follows.

**TypeScript:**

```typescript
// Define the contract first
interface TaskAPI {
  // Creates a task and returns the created task with server-generated fields
  createTask(input: CreateTaskInput): Promise<Task>;

  // Returns paginated tasks matching filters
  listTasks(params: ListTasksParams): Promise<PaginatedResult<Task>>;

  // Returns a single task or throws NotFoundError
  getTask(id: TaskId): Promise<Task>;

  // Partial update — only provided fields change
  updateTask(id: TaskId, input: UpdateTaskInput): Promise<Task>;

  // Idempotent delete — succeeds even if already deleted
  deleteTask(id: TaskId): Promise<void>;
}
```

**Python (Protocol-style contract):**

```python
from typing import Protocol
from .models import Task, TaskId, CreateTaskInput, UpdateTaskInput, ListTasksParams, Page

class TaskAPI(Protocol):
    async def create_task(self, payload: CreateTaskInput) -> Task: ...
    async def list_tasks(self, params: ListTasksParams) -> Page[Task]: ...
    async def get_task(self, task_id: TaskId) -> Task: ...
    async def update_task(self, task_id: TaskId, patch: UpdateTaskInput) -> Task: ...
    async def delete_task(self, task_id: TaskId) -> None: ...
```

A `Protocol` documents the contract independently of any concrete implementation, and both ASGI handlers and in-process callers can satisfy the same shape.

### 2. Consistent Error Semantics

Pick one error strategy and apply it everywhere.

**TypeScript:**

```typescript
interface APIError {
  error: {
    code: string;        // Machine-readable: "VALIDATION_ERROR"
    message: string;     // Human-readable: "Email is required"
    details?: unknown;   // Additional context when helpful
  };
}
```

**Python (FastAPI exception handler):**

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

class APIErrorBody(BaseModel):
    code: str
    message: str
    details: dict | None = None

class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status = status
        self.body = APIErrorBody(code=code, message=message, details=details)

app = FastAPI()

@app.exception_handler(APIError)
async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": exc.body.model_dump()})
```

HTTP status mapping (same in any language):

| Status | Meaning |
|---|---|
| 400 | Client sent invalid data |
| 401 | Not authenticated |
| 403 | Authenticated but not authorized |
| 404 | Resource not found |
| 409 | Conflict (duplicate, version mismatch) |
| 422 | Validation failed (semantically invalid) |
| 500 | Server error (never expose internal details) |

**Don't mix patterns.** If some endpoints throw, others return null, others return `{ error }`, consumers can't predict behavior.

### 3. Validate at Boundaries

Trust internal code; validate at system edges where external input enters. See `references/security-checklist.md` for the full input-validation checklist (boundary-only validation, schema libraries, allow-listing, untrusted-data handling).

**TypeScript:**

```typescript
app.post('/api/tasks', async (req, res) => {
  const result = CreateTaskSchema.safeParse(req.body);
  if (!result.success) {
    return res.status(422).json({
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Invalid task data',
        details: result.error.flatten(),
      },
    });
  }
  const task = await taskService.create(result.data);
  return res.status(201).json(task);
});
```

**Python (FastAPI + Pydantic — validation is automatic at the route boundary):**

```python
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/tasks")

class CreateTaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

class Task(BaseModel):
    id: str
    title: str
    description: str | None
    created_at: str

@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(payload: CreateTaskInput) -> Task:
    # `payload` is already validated. Internal code can trust it.
    return await task_service.create(payload)
```

FastAPI returns a 422 with field-level details automatically when `payload` fails Pydantic validation — no manual `safeParse` branch needed.

Where validation belongs:
- API route handlers (user input)
- Form submission handlers (user input)
- External service response parsing (third-party data — **always treat as untrusted**)
- Environment variable loading (configuration; use `pydantic-settings` or `BaseSettings`)

> **Third-party API responses are untrusted data.** Validate their shape and content before using them in any logic, rendering, or decision-making. A compromised or misbehaving external service can return unexpected types, malicious content, or instruction-like text.

Where validation does NOT belong:
- Between internal functions that share type contracts
- In utility functions called by already-validated code
- On data that just came from your own database (already shaped by your ORM models)

### 4. Prefer Addition Over Modification

Extend interfaces without breaking existing consumers.

**TypeScript:**

```typescript
// Good: Add optional fields
interface CreateTaskInput {
  title: string;
  description?: string;
  priority?: 'low' | 'medium' | 'high';
  labels?: string[];
}

// Bad: Change existing field types or remove fields
interface CreateTaskInput {
  title: string;
  // description: string;  // Removed — breaks existing consumers
  priority: number;         // Type-changed — breaks existing consumers
}
```

**Python:**

```python
class CreateTaskInput(BaseModel):
    title: str
    description: str | None = None
    priority: Literal["low", "medium", "high"] | None = None  # Added later
    labels: list[str] = Field(default_factory=list)           # Added later, default empty
```

New fields are additive when they have defaults (`= None` or `default_factory=list`). Removing a field, tightening a type, or making an optional field required are all breaking changes — bump the version or use a deprecation header.

### 5. Predictable Naming

| Pattern | Convention | Example |
|---|---|---|
| REST endpoints | Plural nouns, no verbs | `GET /api/tasks`, `POST /api/tasks` |
| Query params | camelCase (or snake_case in Python idiomatic APIs — pick one) | `?sortBy=createdAt&pageSize=20` |
| Response fields | camelCase or snake_case (consistent across the API) | `{ "createdAt": ... }` or `{ "created_at": ... }` |
| Boolean fields | `is`/`has`/`can` prefix | `isComplete`, `has_attachments` |
| Enum values | UPPER_SNAKE | `"IN_PROGRESS"`, `"COMPLETED"` |

Pick one convention per API and document it. Mixed `camelCase` and `snake_case` in the same payload is the most common preventable consumer-side bug.

## REST API Patterns

### Resource Design

```
GET    /api/tasks              → List tasks (with query params for filtering)
POST   /api/tasks              → Create a task
GET    /api/tasks/:id          → Get a single task
PATCH  /api/tasks/:id          → Update a task (partial)
DELETE /api/tasks/:id          → Delete a task

GET    /api/tasks/:id/comments → List comments for a task (sub-resource)
POST   /api/tasks/:id/comments → Add a comment to a task
```

### Pagination

Paginate every list endpoint. Two common shapes:

**Offset/limit (TypeScript request + response):**

```typescript
GET /api/tasks?page=1&pageSize=20&sortBy=createdAt&sortOrder=desc

{
  "data": [...],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "totalItems": 142,
    "totalPages": 8
  }
}
```

**Cursor-based (FastAPI):**

```python
from typing import Generic, TypeVar
from pydantic import BaseModel
from fastapi import Query

T = TypeVar("T")

class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None  # opaque; clients pass back unchanged

@router.get("", response_model=Page[Task])
async def list_tasks(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> Page[Task]:
    items, next_cursor = await task_repo.page(cursor=cursor, limit=limit)
    return Page(items=items, next_cursor=next_cursor)
```

Cursor pagination beats offset for large/changing datasets (no skipped or duplicated rows during inserts) and avoids the deep-page `OFFSET 100000` performance cliff.

### Filtering

Use query parameters for filters:

```
GET /api/tasks?status=in_progress&assignee=user123&createdAfter=2025-01-01
```

### Partial Updates (PATCH)

Accept partial objects — only update what's provided.

**TypeScript:**

```typescript
PATCH /api/tasks/123
{ "title": "Updated title" }
```

**Python (Pydantic `model_dump(exclude_unset=True)` for true PATCH semantics):**

```python
class UpdateTaskInput(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: Literal["low", "medium", "high"] | None = None

@router.patch("/{task_id}", response_model=Task)
async def update_task(task_id: str, patch: UpdateTaskInput) -> Task:
    # Only fields the client actually sent — `None` defaults are excluded.
    changes = patch.model_dump(exclude_unset=True)
    return await task_repo.update(task_id, changes)
```

The key trick is `exclude_unset=True`: a client that sends `{"description": null}` (explicit clear) is distinguishable from one that sends `{}` (no change). PUT-only APIs lose this distinction.

## Type System Patterns

### Discriminated Unions for Variants

**TypeScript:**

```typescript
type TaskStatus =
  | { type: 'pending' }
  | { type: 'in_progress'; assignee: string; startedAt: Date }
  | { type: 'completed'; completedAt: Date; completedBy: string }
  | { type: 'cancelled'; reason: string; cancelledAt: Date };

function getStatusLabel(status: TaskStatus): string {
  switch (status.type) {
    case 'pending':     return 'Pending';
    case 'in_progress': return `In progress (${status.assignee})`;
    case 'completed':   return `Done on ${status.completedAt.toISOString()}`;
    case 'cancelled':   return `Cancelled: ${status.reason}`;
  }
}
```

**Python (Pydantic discriminated union with `Literal` tags):**

```python
from datetime import datetime
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

class TextEvent(BaseModel):
    type: Literal["text"]
    body: str

class ImageEvent(BaseModel):
    type: Literal["image"]
    url: str
    width: int
    height: int

class AudioEvent(BaseModel):
    type: Literal["audio"]
    url: str
    duration_ms: int

# `discriminator="type"` lets Pydantic dispatch on the tag at parse time
Event = Annotated[Union[TextEvent, ImageEvent, AudioEvent], Field(discriminator="type")]

class Envelope(BaseModel):
    event: Event

def render(event: Event) -> str:
    match event:
        case TextEvent(body=body):
            return body
        case ImageEvent(url=url, width=w, height=h):
            return f"<img src={url!r} {w}x{h}>"
        case AudioEvent(url=url, duration_ms=ms):
            return f"<audio src={url!r} {ms}ms>"
```

`match`/`case` with the model classes gives you exhaustiveness via mypy/pyright the same way `switch` on a string tag does in TypeScript.

### Branded / Nominal Types for IDs

**TypeScript:**

```typescript
type TaskId = string & { readonly __brand: 'TaskId' };
type UserId = string & { readonly __brand: 'UserId' };

function getTask(id: TaskId): Promise<Task> { /* ... */ }

// Compile error: `string` is not assignable to `TaskId`
// getTask("abc-123");
```

**Python (`typing.NewType`):**

```python
from typing import NewType

UserId = NewType("UserId", int)
TaskId = NewType("TaskId", str)

def get_task(task_id: TaskId) -> Task: ...

# At runtime these are plain int/str — zero overhead.
# At type-check time, mypy/pyright reject `get_task("abc-123")`
# unless you wrap: `get_task(TaskId("abc-123"))`.
```

### Immutable Value Objects (frozen dataclasses)

For domain values that should never mutate after construction:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Money:
    amount_cents: int
    currency: str

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("currency mismatch")
        return Money(self.amount_cents + other.amount_cents, self.currency)

# usd = Money(100, "USD"); usd.amount_cents = 200  # AttributeError — frozen
```

`frozen=True` makes instances hashable and safe to share across threads/tasks. `slots=True` cuts memory and prevents accidental attribute additions.

### Input/Output Separation

Always model "what the caller sends" separately from "what the server returns" — server-generated fields (`id`, `created_at`, `updated_at`) belong only on the output type.

```python
class CreateTaskInput(BaseModel):
    title: str
    description: str | None = None

class Task(BaseModel):
    id: TaskId
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    created_by: UserId
```

The same separation in TypeScript uses two `interface` declarations; the discipline is identical.

## Common Rationalizations

| Rationalization | Why it's wrong |
|---|---|
| "We'll document the API later" | The types ARE the documentation. Define them first; OpenAPI/JSON Schema falls out for free from Pydantic/Zod. |
| "We don't need pagination for now" | You will the moment someone has 100+ items. Adding pagination later is a breaking change. |
| "PATCH is complicated, let's just use PUT" | PUT requires the full object every time and loses the explicit-null vs absent distinction. PATCH with `exclude_unset` is what clients actually want. |
| "We'll version the API when we need to" | Breaking changes without versioning break consumers silently. Design for extension (additive optional fields, deprecation headers) from the start. |
| "Nobody uses that undocumented behavior" | Hyrum's Law: if it's observable, somebody depends on it. Treat every public behavior as a commitment, including error message text and response ordering. |
| "We can just maintain two versions" | Multiple versions multiply maintenance cost and create diamond dependency problems. Prefer the One-Version Rule with additive changes. |
| "Internal APIs don't need contracts" | Internal consumers are still consumers. Protocol classes (Python) and `interface` declarations (TS) prevent coupling and enable parallel work. |
| "Validation in the service layer is fine" | Boundary-only validation is the security invariant — see `references/security-checklist.md`. Service-layer-only validation means ad-hoc bypasses leak in. |

## Red Flags

- Endpoints that return different response shapes depending on conditions (a search endpoint that returns `Task[]` for one query and `{results: Task[]}` for another).
- Inconsistent error formats across endpoints (some throw, some return `{ok: false}`, some return HTTP 200 with an error body).
- Validation scattered throughout internal code instead of at boundaries.
- Breaking changes to existing fields (type changes, removals, required-flag flips) shipped without a version bump.
- List endpoints without pagination or with pagination params that silently cap at the database default.
- Verbs in REST URLs (`/api/createTask`, `/api/getUsers`).
- Third-party API responses or webhook payloads consumed without a Pydantic/Zod parse step.
- Discriminated-union types missing the discriminant field, forcing consumers to guess via `in`/`hasattr` checks.
- ID parameters typed as bare `string` / `int` everywhere, allowing a `UserId` to be passed where a `TaskId` is expected.

## Verification

1. Every endpoint has a typed input schema (Pydantic model or Zod schema) and a typed output schema (response_model in FastAPI, return-type annotation in TS).
2. All error responses across the API conform to one documented shape; cite the shared error type or exception handler.
3. Validation is performed only at boundaries — no `model_validate` / `safeParse` calls inside service-layer code that already received typed input.
4. Every list endpoint returns a `Page[T]`-shaped response (or equivalent) and rejects `limit` values above a documented maximum.
5. New fields added in this change are optional with defaults; show the diff against the previous schema.
6. Discriminated unions use a tag field (`type: Literal[...]` in Python, `type: '...'` in TS) and are dispatched with `match` / `switch` rather than ad-hoc property checks.
7. ID parameters use `NewType` (Python) or branded types (TS) at every public function boundary; show one call site that would fail type-checking if the wrong ID were passed.
