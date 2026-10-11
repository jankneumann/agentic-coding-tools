## ADDED Requirements

### Requirement: Review Spend Recording Route

The coordinator SHALL expose `POST /routing/spend`, which requires the `X-API-Key` header.

The request body SHALL be validated with unknown fields forbidden. It accepts:
- required: `vendor`, `model`, `endpoint_kind`, `generation_id`;
- optional: `prompt_tokens`, `completion_tokens` (non-negative integers), `actual_usd` (a
  non-negative number), `tokens_estimated`, `work_unit_ref`, `occurred_at`.

A valid request SHALL write one `routing_spend_ledger` row through `LedgerService.record`.
`generation_id` SHALL be the idempotency key: a second request with a `generation_id` already
in the ledger SHALL return the existing row with HTTP 200 and SHALL NOT insert another row.
`GET /routing/usage` SHALL include recorded review rows in `metered_usd_used`.

#### Scenario: A review spend row is recorded
- **WHEN** an authenticated client posts `{vendor: "openrouter", model: "<publisher>/<model>", endpoint_kind: "openrouter", generation_id: "gen-abc", actual_usd: 0.0042, tokens_estimated: false}`
- **THEN** the response SHALL be HTTP 201, and the next `GET /routing/usage?window=month` SHALL
  report `metered_usd_used` increased by 0.0042

#### Scenario: Duplicate generation id is not double-counted
- **WHEN** the same body is posted twice
- **THEN** the second response SHALL be HTTP 200 and the ledger SHALL contain one `gen-abc` row

#### Scenario: Unauthenticated write is rejected
- **WHEN** the request has no `X-API-Key` header, or an invalid one
- **THEN** the response SHALL be HTTP 401 and no row SHALL be written

#### Scenario: Invalid spend is rejected
- **WHEN** the body has `actual_usd: -1`, or an unknown field `api_key`
- **THEN** the response SHALL be HTTP 422 and no row SHALL be written
