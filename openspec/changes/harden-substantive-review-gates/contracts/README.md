# Contracts

This change was evaluated for OpenAPI, database, event, and generated-type contracts. None apply: it modifies an internal Python callback and convergence policy without changing a network, database, or event interface.

The internal callback contract is documented by design decision D3 and tested directly:

```text
result_callback(result: ReviewResult, expected_count: int) -> None
```

The callback is optional, receives each terminal result exactly once, and may raise to fail the dispatch closed when durable persistence fails.
