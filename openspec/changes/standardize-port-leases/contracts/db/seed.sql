-- Test fixtures for port_leases contract tests.
INSERT INTO port_leases (slot, session_id, agent_id, db_port, rest_port, realtime_port, api_port, ui_port,
                         compose_project_name, isolation_provided, allocated_at, expires_at)
VALUES
  (0, 'sess-active-1', 'agent-a', 10000, 10001, 10002, 10003, 10004, 'ac-0a1b2c3d', FALSE, now(), now() + interval '2 hours'),
  (1, 'sess-expired-1', 'agent-b', 10100, 10101, 10102, 10103, 10104, 'ac-1b2c3d4e', FALSE, now() - interval '5 hours', now() - interval '1 hour');

-- A blocked slot with no session (design D6).
INSERT INTO port_leases (slot, session_id, agent_id, db_port, rest_port, realtime_port, api_port, ui_port,
                         blocked_until, block_reason)
VALUES
  (2, NULL, NULL, 10200, 10201, 10202, 10203, 10204, now() + interval '30 minutes', 'bind_failed:10201');
