# Build instruction index with stable AG-nnn ids and memory-surface hash

> Parent roadmap: `backpass-memory-alignment`
> Change ID: `build-instruction-index-and-surface-hash`
> Effort: M
> Priority: 3

## Summary

Add a shared script that parses AGENTS.md into units (list items and paragraphs under headings), hashes each, assigns stable AG-nnn aliases that survive reordering, and computes a surface hash over the memory file plus every skill description line. Expose both as importable functions and a CLI.

## Dependencies

- `ri-01`
- `ri-02`

## Acceptance Outcomes

- Running the index CLI over AGENTS.md emits a JSON list of units each with id (AG-nnn), content hash, heading path, and line range; reordering two sections leaves every id unchanged.
- Editing one skill description changes the surface hash; editing README.md does not (asserted by test).
- The instruction index produced matches the ids backpass reported in the ri-01 spike for the same file version, or the difference is documented.

## Rationale

Adopt items 2 and 7 in section 4. Attribution of evidence to a specific instruction is the missing piece that lets the pipeline justify removing a line, not only adding one; the surface hash is the cache key that invalidates exactly the evidence an edit depends on. If the spike chose backpass as engine this wraps its index output; if it chose port this is the Python equivalent of src/memory.js.
