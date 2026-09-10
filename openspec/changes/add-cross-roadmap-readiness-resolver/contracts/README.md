# Readiness resolver contracts

This change adds no HTTP, database, or event interface, so no OpenAPI/database/event contract applies. The command's stable JSON stdout is contracted by `readiness-result.schema.json`; stderr and the non-zero status for invalid canonical state remain operational diagnostics.

