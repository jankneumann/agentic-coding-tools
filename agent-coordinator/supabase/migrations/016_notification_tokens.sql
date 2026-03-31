CREATE TABLE IF NOT EXISTS notification_tokens (
    token TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    change_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ
);
CREATE INDEX idx_notification_tokens_expires ON notification_tokens (expires_at) WHERE used_at IS NULL;
