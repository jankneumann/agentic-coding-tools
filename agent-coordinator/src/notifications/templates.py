"""HTML email templates for coordinator notifications."""

from __future__ import annotations

import html as html_mod

from src.event_bus import CoordinatorEvent


def _esc(value: str) -> str:
    """Escape a value for safe HTML embedding."""
    return html_mod.escape(str(value))


def _sanitize_header(value: str) -> str:
    """Strip newlines/carriage returns to prevent email header injection."""
    return value.replace("\n", " ").replace("\r", " ")


# Shared dark-terminal CSS — long lines are intentional (inline CSS)
_STYLE = """
<style>
  body { background: #1e1e2e; color: #cdd6f4;
    font-family: 'Courier New', monospace; margin: 0; padding: 20px; }
  .container { max-width: 600px; margin: 0 auto;
    background: #181825; border: 1px solid #313244;
    border-radius: 8px; padding: 24px; }
  h1 { color: #89b4fa; font-size: 18px; margin-top: 0; }
  h2 { color: #a6adc8; font-size: 14px; }
  .field { margin: 8px 0; }
  .label { color: #6c7086; }
  .value { color: #cdd6f4; }
  .urgent { color: #f38ba8; font-weight: bold; }
  .info { color: #94e2d5; }
  .reply-box { background: #313244; border: 1px solid #45475a;
    border-radius: 4px; padding: 12px; margin-top: 16px; }
  .reply-box code { color: #f9e2af; }
  .separator { border-top: 1px solid #313244; margin: 16px 0; }
  .footer { color: #6c7086; font-size: 11px; margin-top: 16px; }
  .event-item { border-left: 3px solid #89b4fa;
    padding-left: 12px; margin: 8px 0; }
</style>
"""


def _wrap(body_html: str) -> str:
    """Wrap body content in the shared HTML template."""
    return (
        f"<!DOCTYPE html>\n<html>\n"
        f"<head><meta charset=\"utf-8\">{_STYLE}</head>\n"
        f"<body><div class=\"container\">{body_html}</div></body>\n"
        f"</html>"
    )


def _change_label(event: CoordinatorEvent) -> str:
    cid = _esc(event.change_id or "unknown")
    return f"change <span class='info'>{cid}</span>"


def _field(label: str, value: str, cls: str = "value") -> str:
    """Render a single field div."""
    return (
        f'<div class="field">'
        f'<span class="label">{label}:</span> '
        f'<span class="{cls}">{_esc(value)}</span>'
        f"</div>"
    )


def render_approval_email(
    event: CoordinatorEvent, token: str
) -> tuple[str, str]:
    """Render approval request email. Returns (subject, html_body)."""
    subject = _sanitize_header(
        f"[coordinator] Approval needed: {event.summary} [#{token}]"
    )
    urgency_cls = "urgent" if event.urgency == "high" else "value"
    body = _wrap(f"""
    <h1>Approval Request</h1>
    {_field("Change", event.change_id or "unknown")}
    {_field("Event", event.event_type)}
    {_field("Agent", event.agent_id)}
    {_field("Summary", event.summary)}
    {_field("Urgency", event.urgency, urgency_cls)}
    <div class="separator"></div>
    <div class="reply-box">
        <h2>Reply Instructions</h2>
        <p>Reply to this email with one of:</p>
        <p><code>approved</code> &mdash; approve the request</p>
        <p><code>denied</code> &mdash; reject the request</p>
    </div>
    <div class="footer">
      Token: {_esc(token)} | Entity: {_esc(event.entity_id)}
    </div>
    """)
    return subject, body


def render_status_email(
    event: CoordinatorEvent,
) -> tuple[str, str]:
    """Render status update email. Returns (subject, html_body)."""
    subject = _sanitize_header(
        f"[coordinator] {event.event_type}: {event.summary}"
    )
    body = _wrap(f"""
    <h1>Status Update</h1>
    {_field("Change", event.change_id or "unknown")}
    {_field("Event", event.event_type)}
    {_field("Agent", event.agent_id)}
    {_field("Summary", event.summary)}
    {_field("Urgency", event.urgency)}
    <div class="footer">Entity: {_esc(event.entity_id)}</div>
    """)
    return subject, body


def render_escalation_email(
    event: CoordinatorEvent, token: str
) -> tuple[str, str]:
    """Render escalation email. Returns (subject, html_body)."""
    subject = _sanitize_header(
        f"[coordinator] ESCALATION: {event.summary} [#{token}]"
    )
    body = _wrap(f"""
    <h1 class="urgent">Escalation</h1>
    {_field("Change", event.change_id or "unknown")}
    {_field("Event", event.event_type)}
    {_field("Agent", event.agent_id)}
    {_field("Summary", event.summary, "value urgent")}
    <div class="separator"></div>
    <div class="reply-box">
        <h2>Reply Instructions</h2>
        <p>This event requires your attention. Reply with:</p>
        <p><code>resolved</code> &mdash; re-trigger gate check</p>
        <p><code>skip</code> &mdash; bypass current phase</p>
        <p>Or free text with guidance for the next round.</p>
    </div>
    <div class="footer">
      Token: {_esc(token)} | Entity: {_esc(event.entity_id)}
    </div>
    """)
    return subject, body


def render_stale_agent_email(
    event: CoordinatorEvent,
) -> tuple[str, str]:
    """Render stale agent alert email. Returns (subject, html_body)."""
    subject = _sanitize_header(
        f"[coordinator] Stale agent: {event.agent_id}"
    )
    body = _wrap(f"""
    <h1 class="urgent">Stale Agent Detected</h1>
    {_field("Agent", event.agent_id)}
    {_field("Event", event.event_type)}
    {_field("Summary", event.summary)}
    {_field("Last seen", event.timestamp)}
    <div class="footer">Entity: {_esc(event.entity_id)}</div>
    """)
    return subject, body


def render_digest_email(
    events: list[CoordinatorEvent],
) -> tuple[str, str]:
    """Render a digest of multiple events. Returns (subject, html_body)."""
    count = len(events)
    subject = (
        f"[coordinator] Digest: {count} event"
        f"{'s' if count != 1 else ''}"
    )
    items_html = ""
    for ev in events:
        change = _esc(ev.change_id or "n/a")
        items_html += f"""
        <div class="event-item">
            <div class="field">
              <span class="label">{_esc(ev.event_type)}</span>
            </div>
            <div class="field">
              <span class="value">{_esc(ev.summary)}</span>
            </div>
            <div class="field">
              <span class="label">Agent:</span> {_esc(ev.agent_id)}
              | <span class="label">Change:</span> {change}
            </div>
        </div>
        """
    body = _wrap(f"""
    <h1>Event Digest ({count} events)</h1>
    {items_html}
    <div class="footer">Generated at batch time</div>
    """)
    return subject, body
