# Contracts: cloudflare-domain-setup

## Evaluated Contract Sub-Types

| Sub-Type | Applicable? | Reason |
|----------|-------------|--------|
| OpenAPI | No | No new API endpoints introduced. Existing endpoints are accessed through the tunnel without changes. |
| Database | No | No database schema changes. |
| Event | No | No new events introduced. |
| Type generation | No | No new types or models. |

## Summary

This change is infrastructure/configuration only. It introduces:
- A Cloudflare Tunnel config template (YAML)
- A deployment profile (YAML)
- A Docker Compose service addition
- Documentation

No API contracts change — the tunnel is transparent to the application layer. Cloud agents use the same HTTP endpoints with different URLs (custom domain instead of Railway domain).
