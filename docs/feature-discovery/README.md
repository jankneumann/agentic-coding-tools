# Feature Discovery Artifacts

Machine-readable outputs produced by `/explore-feature`.

## Files

- `opportunities.json`: Latest ranked opportunity list.
- `history.json`: Recent top recommendations with timestamp, status, and rationale.

## opportunities.json shape

```json
{
  "generated_at": "2026-02-17T00:00:00Z",
  "focus_area": "performance",
  "weights": {
    "impact": 0.4,
    "strategic_fit": 0.25,
    "effort": 0.2,
    "risk": 0.15
  },
  "items": [
    {
      "id": "refactor-guardrail-cache",
      "title": "Reduce repeated policy lookups",
      "score": 2.55,
      "bucket": "quick-win",
      "impact": "high",
      "strategic_fit": "high",
      "effort": "S",
      "risk": "low",
      "blocked_by": []
    }
  ]
}
```

## history.json shape

```json
{
  "updated_at": "2026-02-17T00:00:00Z",
  "recommendations": [
    {
      "opportunity_id": "refactor-guardrail-cache",
      "recommended_at": "2026-02-17T00:00:00Z",
      "status": "deferred",
      "reason": "waiting for policy migration"
    }
  ]
}
```
