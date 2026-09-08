# Contracts

Ri-09 reuses the ri-08 work-queue projection contracts unchanged. The adapter maps `LoopState.change_id`, `current_phase`, and `total_iterations` to the existing `projection_key` fields `change_id`, `phase`, and `transition_sequence`. Reserved identity fields are never duplicated in `input_data`, and queue responses are observability-only.
