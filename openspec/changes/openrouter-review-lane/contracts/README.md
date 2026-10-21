# Contracts

- `config/routing-cost-policy.schema.json` supersedes the archived
  `declare-the-routing-cost-policy-the-router-obeys` ladder schema: it adds the
  `metered-api-cloud` tier (design D1) and allows a fourth rung. The archive is
  left unchanged as history.
- `config/routing.schema.json` supersedes the
  `implement-the-task-router-vendor-x-location-x-model` routing policy schema with
  the same tier. That change's own contract is left as it was written.

Both are what the deployed `agent-coordinator/routing.yaml` validates against
(`tests/model_routing/test_routing_cost_policy.py`,
`tests/model_routing/test_routing_policy_config.py`). When this change archives,
`change_dir()` resolves the archived path.
