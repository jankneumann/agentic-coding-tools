# Contracts

- `db/schema.sql` defines the projection-key unique index and reconciliation RPC boundary.
- `openapi/v1.yaml` defines additive `/work/submit` result fields and the new `/work/reconcile` endpoint.

The contracts deliberately do not define a kanban or live phase event. ri-09 owns live mirroring.
