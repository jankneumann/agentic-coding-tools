# Vendor registry contracts

- `openapi/v1.yaml`: authenticated registry read and rate-limit ingestion surface.
- `db/schema.sql`: additive runtime-state tables; deliberately contains no cost columns.
- `events/vendor-availability.schema.json`: normalized watchdog and dispatcher observation shape.

Model pricing remains owned by dg-00 `model_catalog`; registry responses project catalog rows.
