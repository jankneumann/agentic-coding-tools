"""The Langfuse helper authenticates only with coordinator-internal inputs."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "langfuse_env.sh"


def test_internal_approle_inputs_and_legacy_inputs_ignored(tmp_path: Path) -> None:
    curl = tmp_path / "curl"
    curl.write_text("""#!/usr/bin/env bash
case \"${*: -1}\" in
  */auth/approle/login)
    [[ \"$*\" == *'internal-role'* && \"$*\" == *'internal-secret'* ]] || exit 7
    printf '%s' '{"auth":{"client_token":"internal-token"}}'
    ;;
  */secret/data/coordinator)
    [[ \"$*\" == *'X-Vault-Token: internal-token'* ]] || exit 8
    printf '%s' '{"data":{"data":{"LANGFUSE_PUBLIC_KEY":"public","LANGFUSE_SECRET_KEY":"secret","LANGFUSE_HOST":"https://example.test"}}}'
    ;;
  *) exit 9 ;;
esac
""", encoding="utf-8")
    curl.chmod(0o700)
    env = {"PATH": f"{tmp_path}:{os.environ['PATH']}", "BAO_ADDR": "http://bao.test",
           "BAO_INTERNAL_ROLE_ID": "internal-role", "BAO_INTERNAL_SECRET_ID": "internal-secret",
           "BAO_ROLE_ID": "old-role", "BAO_SECRET_ID": "old-secret"}
    output = subprocess.run(["bash", str(SCRIPT)], env=env, text=True, capture_output=True, check=True)
    assert "export LANGFUSE_PUBLIC_KEY=public" in output.stdout
    assert "export LANGFUSE_SECRET_KEY=secret" in output.stdout
    assert "export LANGFUSE_HOST=https://example.test" in output.stdout
    assert "cHVibGljOnNlY3JldA==" in output.stdout
    assert "old-role" not in output.stdout + output.stderr


def test_legacy_approle_inputs_cannot_authenticate(tmp_path: Path) -> None:
    curl = tmp_path / "curl"
    curl.write_text("#!/usr/bin/env bash\necho called >&2\nexit 1\n", encoding="utf-8")
    curl.chmod(0o700)
    env = {"PATH": f"{tmp_path}:{os.environ['PATH']}", "BAO_ADDR": "http://bao.test",
           "BAO_ROLE_ID": "old-role", "BAO_SECRET_ID": "old-secret"}
    output = subprocess.run(["bash", str(SCRIPT)], env=env, text=True, capture_output=True, check=True)
    assert "called" not in output.stderr
    assert output.stdout == ""
