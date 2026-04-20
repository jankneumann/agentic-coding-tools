# Contracts: migrate-fastmcp-3x

## Evaluation

| Sub-type | Applicable? | Rationale |
|----------|-------------|-----------|
| OpenAPI | No | No new/modified API endpoints — this is an internal library migration |
| Database | No | No schema changes |
| Events | No | No event payload changes |
| Type generation | No | No new interfaces — existing MCP tool signatures preserved |

## Notes

This migration preserves all existing MCP tool signatures (names, parameters, return types) and resource URIs. The change is purely in the framework version and transport mechanism, not in the public interface exposed to MCP clients.

The 28 tool signatures and 10 resource URIs serve as the implicit contract — any change to these would be a breaking change for connected agents and is explicitly out of scope for this migration.
