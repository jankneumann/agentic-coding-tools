# Grounding and coverage disclosure

This reference is the contract for when a sketch is graph-backed versus
source-read, and for the mandatory `Grounding:` line on every sketching reply.

## Freshness (`--check`)

Before sketching a **call tree**, run:

```bash
python3 "<skill-base-dir>/../refresh-architecture/scripts/run_architecture.py" --check
```

Treat **exit code `0` alone** as fresh. Do **not** use `build_atlas.py --check`
(that flag means HTML-page drift, exit `2`).

Before invoking `--check`:

- If the `--check` script or the architecture graph file is missing → reason
  `graph absent` (do not spawn `--check`).

When spawning `--check`:

- OSError / exception before an exit code → `graph check failed`
- Non-zero exit (including `1` for stale provenance) → `graph stale`

The skill **never** runs `--ensure` or the analysis pipeline.

## Call tree from `--tree`

When `--check` exited `0`, obtain callers/callees with:

```bash
python3 "<skill-base-dir>/../codebase-atlas/scripts/build_atlas.py" --tree <target> [--hops N] [--direction in|out|both]
```

Build the call tree **only** from nodes that `--tree` prints. Do not invent
symbols.

`--tree` exits:

| Exit | Meaning | Skill reaction |
|---|---|---|
| `0` | Tree printed | Grounded call tree + grounded disclosure |
| `1` | Input/IO error | Source fallback; reason `graph check failed` |
| `2` | Target not found | Source fallback; reason `symbol not in graph` |
| `3` | Ambiguous name (sorted candidate ids on stderr) | List candidates and **ask**; no source fallback; **no** `Grounding:` line |
| other / spawn failure | Unexpected | Source fallback; reason `graph check failed` |

After a fresh `--check`, if `--tree` cannot be spawned or returns any exit other
than `0`/`2`/`3`, use `graph check failed`.

## Disclosure line (sketching replies only)

Exactly one final line. Two reply shapes are **exempt** and MUST NOT carry
`Grounding:`:

1. **Ambiguous-symbol clarification** (`--tree` exit `3`)
2. **Whole-repository redirect** (name `/codebase-atlas` and stop)

### Grounded call tree

Take the `--tree` footer (`graph @ <sha7> · <list> covered`). Copy the substring
**after** `· ` and **before** the trailing ` covered`, then re-append ` covered`.
Use `; ` after the sha (not the footer's `·`):

```text
Grounding: graph @ <sha7>; <language> <percent>% / <language> <percent>% covered
```

Preserve language order, ` / ` separators, and one-decimal percents. Percentages
are the atlas optimistic upper bound (basename matching).

### Ungrounded / non-graph-backed

```text
Grounding: source read, unverified (<reason>)
```

`<reason>` is exactly one of these, **first match wins**:

1. `graph absent` — script or graph missing before `--check`
2. `graph check failed` — `--check` could not be spawned; or after a fresh
   `--check`, `--tree` could not be spawned, exits `1`, or returns any exit
   other than `0`/`2`/`3`
3. `graph stale` — `--check` ran and exited non-zero
4. `symbol not in graph` — `--tree` exited `2`
5. `form not graph-backed` — catalogue form other than a call tree

Only a call tree built from `--tree` after a fresh `--check` may use the
grounded form.

## Non-call-tree forms

For component tree, file tree, sequence, or structural diff: **read the
relevant source files before sketching**, then disclose with
`form not graph-backed`. Never claim the grounded `graph @` form for those.

## Ask, don't guess

On `--tree` exit `3`, print the candidate ids from stderr and ask which was
meant. Do not pick one. Do not fall back to source for a guessed symbol.

## Whole-repository questions

Name `/codebase-atlas` and stop. No visual. No `Grounding:` line.

## Refusals (D9)

- Do not write files. Text and Mermaid go inline in the reply only.
- Do not open a browser.
- Do not answer "show me the whole architecture"; redirect as above.
