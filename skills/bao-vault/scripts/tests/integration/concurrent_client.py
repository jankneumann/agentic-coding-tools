"""Child process for the live one-use bootstrap contention assertion."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

from openbao_credentials import OpenBaoClient, PrincipalOpenBaoConfig


def main() -> None:
    addr, directory, principal_id, role_name, ready_name, start_name = sys.argv[1:]
    client = OpenBaoClient(PrincipalOpenBaoConfig(addr=addr, bootstrap_dir=Path(directory)))
    calls = {"unwrap": 0, "login": 0}
    unwrap = client.client.sys.unwrap
    login = client.client.auth.approle.login

    def counted_unwrap(*args, **kwargs):
        calls["unwrap"] += 1
        return unwrap(*args, **kwargs)

    def counted_login(*args, **kwargs):
        calls["login"] += 1
        return login(*args, **kwargs)

    client.client.sys.unwrap = counted_unwrap
    client.client.auth.approle.login = counted_login
    Path(ready_name).touch()
    deadline = time.monotonic() + 10
    while not Path(start_name).exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("contention start barrier timed out")
        time.sleep(0.01)
    session = client.ensure_session(principal_id, role_name)
    # Only a digest crosses the process boundary; no live token reaches stdout.
    print(json.dumps({"token_digest": hashlib.sha256(session.client_token.encode()).hexdigest(),
                      **calls}))


if __name__ == "__main__":
    main()
