# Enablement gate — integrated-tree mutation proof (task 7.2)

Task 5.5 proved the gate's *logic* discriminates via
[`packages/context-eval/tests/test_enablement_gate_mutation.py`](../../../packages/context-eval/tests/test_enablement_gate_mutation.py)
and noted that the `make` wiring had been checked separately, on a scratch
tree, before phase 7 existed. This artifact is that check repeated as a
durable record, on the fully integrated `openspec/gate-semantic-context-default-enablement`
branch, per design decision D14 ("a gate that was never shown to fail is not
evidence that it works").

## Method

1. Confirmed the gate is green on the unmodified integrated tree
   (`INJECTION_DEFAULT_ENABLED = False`, `report.json` verdict `fail`):
   `make semantic-enablement-gate` exits `0`.
2. Cleared every `__pycache__` directory outside `.venv`/`node_modules` so no
   stale bytecode could mask the mutation.
3. Flipped `INJECTION_DEFAULT_ENABLED` from `False` to `True` in
   `skills/context-engineering/scripts/semantic_context.py` — the single
   named declaration the gate reads — and committed it alone as a scratch
   commit: `84120599a2d8e5f3c995d108e70e32d2e26b5a8d`.
4. Ran the gate two ways: the underlying module directly (to see its own exit
   code) and through `make semantic-enablement-gate` (to see what CI actually
   observes, since `make` collapses the target's exit code to its own `2` on
   failure while printing the real one).
5. Reverted the flip in the very next commit and confirmed the working tree
   is byte-identical to the pre-flip state (`git diff HEAD~1 -- skills/context-engineering/scripts/semantic_context.py`
   was empty) and that the gate is green again.

## Result

**Raw module exit code: `3`** (evidence absent/expired — here, the recorded
report does not authorize the flipped default). **`make`'s collapsed exit
code: `2`**, with the real code surfaced in its own error line:

```
make: *** [semantic-enablement-gate] Error 3
```

Full captured stderr from the mutated run:

```
INJECTION_DEFAULT_ENABLED is True in skills/context-engineering/scripts/semantic_context.py, and the evidence at docs/evaluation/semantic-context/report.json does not authorize it.
  unmet condition: embedder_fingerprint_current: the report records embedder fingerprint f5ae15d31080994823bfea9a455808c39f60e592977d74c034081db3506e388d, and no configured embedding contract was supplied (--embedding-contract) to compare it against; an unchecked fingerprint is not a matching one
  unmet condition: indexed_revision_reachable: the report records no indexed revision, so nothing ties the measurement to a tree this one descends from
  unmet condition: verdict_pass: the recorded verdict is 'fail' (unmeasured, denominator_mismatch, index_tier_insufficient); it never authorized anything
Enablement is authorized only by a current, schema-valid, passing report. Either retake the measurement or restore INJECTION_DEFAULT_ENABLED to False.
```

The gate names all three unmet conditions the current `report.json` fails to
satisfy against a flipped default, exactly as designed. After the revert,
`make semantic-enablement-gate` exits `0` again with the same "off by
default, no evidence required" message as the pre-mutation baseline.

## What this does and does not license

This proves the `make` wiring around the enablement gate fails loudly and
correctly when the default is flipped without evidence, on the real
integrated tree rather than a hypothetical one. It does not change the
verdict recorded in [`report.json`](report.json) (`fail`, per phase 6 / D11),
does not narrow the gate's conditions, and does not authorize enabling
semantic context injection. `INJECTION_DEFAULT_ENABLED` remains `False`.
