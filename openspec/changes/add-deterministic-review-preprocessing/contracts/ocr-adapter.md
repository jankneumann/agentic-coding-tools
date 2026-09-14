# OCR adapter contract

## Command

`ocr_adapter.py` is invoked by the dispatcher as the `ocr-local` agent's
review-mode command with the prompt on stdin. It reads `base_ref` and
`head_ref` from the packet meta named in the prompt header and runs:

```
ocr review --format json --audience agent --output <tmpfile> \
    --from <base_ref> --to <head_ref> --background-file <packet body>
```

If `ocr` is not on PATH, or `ocr llm test` fails, the adapter exits 2 with
the reason on stderr so discovery classifies the vendor as unavailable.

## Output rewrite

| OCR comment field | review-findings field | Note |
|---|---|---|
| `path` | `file_path` | verbatim |
| `content` | `description` | verbatim |
| `existing_code` | `existing_code` | verbatim |
| `start_line`, `end_line` | `line_range {start,end}` | omitted when both are 0 |
| `category` | `type` | via coercion sidecar |
| `severity` | `criticality` and `severity` | via coercion sidecar |
| `suggestion_code` | `resolution` | prefixed `Suggested change:` |
| (none) | `axis` | from `type` through `axis_aliases` |
| (none) | `disposition` | `fix` |
| (none) | `id` | `ocr-<n>` |

The payload carries `review_type` from the prompt header, `target` from the
packet `change_id`, `reviewer_vendor: ocr`, and a `coverage` block built from
OCR's per-file review status when present.

## Coercion aliases added to `finding-coercion.json`

| Source key | From | To |
|---|---|---|
| `type_aliases` | `maintainability` | `architecture` |
| `type_aliases` | `test` | `correctness` |
| `type_aliases` | `documentation` | `style` |
| `type_aliases` | `other` | `style` |
| `axis_aliases` | `maintainability` | `architecture` |
| `axis_aliases` | `documentation` | `readability` |
| `criticality_from_ocr_severity` | `critical` | `critical` |
| `criticality_from_ocr_severity` | `high` | `high` |
| `criticality_from_ocr_severity` | `medium` | `medium` |
| `criticality_from_ocr_severity` | `low` | `low` |

`severity` is then filled from `criticality` by the existing map. The
existing `bug`, `security`, `performance`, and `style` keys already resolve.
