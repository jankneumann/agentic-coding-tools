"""Durability and bounded-resource tests for the sandbox audit port."""

import json
import os
from pathlib import Path

import pytest

from shared.sandbox_audit import AuditDeliveryError, CoordinatorAuditSender, SandboxAuditPort


def _event(number: int = 1) -> dict:
    return {"schema_version": 1, "event_id": f"00000000-0000-4000-8000-{number:012d}"}


def test_state_root_must_be_absolute_owned_nonsymlink_and_outside_checkout(tmp_path):
    checkout = tmp_path / "repo"
    checkout.mkdir()
    with pytest.raises(AuditDeliveryError):
        SandboxAuditPort(state_root=Path("relative"), checkout_roots=[checkout])
    with pytest.raises(AuditDeliveryError):
        SandboxAuditPort(state_root=checkout / "state", checkout_roots=[checkout])
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(AuditDeliveryError):
        SandboxAuditPort(state_root=link, checkout_roots=[checkout])


def test_unavailable_endpoint_fsyncs_mode_0600_canonical_jsonl(tmp_path):
    root = tmp_path / "state"
    port = SandboxAuditPort(
        state_root=root,
        checkout_roots=[],
        sender=lambda _event: (_ for _ in ()).throw(OSError("down")),
    )
    result = port.record(_event())
    path = root / "outbox.jsonl"
    assert result.queued is True
    assert (path.stat().st_mode & 0o777) == 0o600
    assert json.loads(path.read_text().strip()) == _event()


def test_live_4xx_fails_closed_without_queueing(tmp_path):
    port = SandboxAuditPort(
        state_root=tmp_path / "state",
        checkout_roots=[],
        sender=lambda _event: (422, {"detail": "invalid"}),
    )
    with pytest.raises(AuditDeliveryError, match="permanent rejection"):
        port.record(_event())
    assert not (tmp_path / "state" / "outbox.jsonl").exists()


def test_drain_moves_permanent_rejection_to_dead_letter_and_continues(tmp_path):
    root = tmp_path / "state"
    calls = []
    port = SandboxAuditPort(
        state_root=root,
        checkout_roots=[],
        sender=lambda _event: (_ for _ in ()).throw(OSError("down")),
    )
    port.record(_event(1))
    port.record(_event(2))

    def sender(event):
        calls.append(event["event_id"])
        return (422, {"detail": "bad"}) if event == _event(1) else (201, {"success": True})

    port.sender = sender
    telemetry = port.drain()
    assert telemetry.permanent_rejections == 1
    assert telemetry.active_records == 0
    dead = json.loads((root / "dead-letter.jsonl").read_text().strip())
    assert dead["event"] == _event(1)
    assert dead["response_status"] == 422
    assert calls == [_event(1)["event_id"], _event(2)["event_id"]]


def test_record_and_active_outbox_bounds_fail_closed(tmp_path):
    port = SandboxAuditPort(
        state_root=tmp_path / "state",
        checkout_roots=[],
        sender=lambda _event: (_ for _ in ()).throw(OSError("down")),
        max_record_bytes=80,
        max_records=1,
    )
    port.record(_event(1))
    with pytest.raises(AuditDeliveryError, match="record limit"):
        port.record(_event(2))
    with pytest.raises(AuditDeliveryError, match="64 KiB"):
        port.record({**_event(3), "padding": "x" * 100})


def test_outbox_permissions_are_repaired_before_use(tmp_path):
    root = tmp_path / "state"
    root.mkdir(mode=0o700)
    outbox = root / "outbox.jsonl"
    outbox.write_text("")
    os.chmod(outbox, 0o644)
    port = SandboxAuditPort(
        state_root=root,
        checkout_roots=[],
        sender=lambda _event: (_ for _ in ()).throw(OSError("down")),
    )
    port.record(_event())
    assert (outbox.stat().st_mode & 0o777) == 0o600


def test_dead_letters_rotate_and_enforce_retained_file_cap(tmp_path):
    root = tmp_path / "state"
    port = SandboxAuditPort(
        state_root=root,
        checkout_roots=[],
        sender=lambda _event: (_ for _ in ()).throw(OSError("down")),
        max_dead_letter_bytes=220,
        max_dead_letter_files=1,
        max_dead_letter_total_bytes=1000,
    )
    port.record(_event(1))
    port.sender = lambda _event: (422, {"detail": "bad"})
    port.drain()
    port.sender = lambda _event: (_ for _ in ()).throw(OSError("down"))
    port.record(_event(2))
    port.sender = lambda _event: (422, {"detail": "bad"})
    port.drain()
    assert len(list(root.glob("dead-letter.*.jsonl"))) == 1

    port.sender = lambda _event: (_ for _ in ()).throw(OSError("down"))
    port.record(_event(3))
    port.sender = lambda _event: (422, {"detail": "bad"})
    with pytest.raises(AuditDeliveryError, match="retained file limit"):
        port.drain()


def test_stdlib_sender_posts_api_key_and_event(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def getcode(self):
            return 201

        def read(self):
            return b'{"success":true}'

    def urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("shared.sandbox_audit.url_request.urlopen", urlopen)
    sender = CoordinatorAuditSender(
        base_url="http://127.0.0.1:3000",
        api_key="test-key",
        timeout_seconds=1.5,
    )
    status, payload = sender(_event())
    assert status == 201
    assert payload == {"success": True}
    assert captured["request"].get_header("X-api-key") == "test-key"
    assert captured["timeout"] == 1.5
