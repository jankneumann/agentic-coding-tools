"""D6: coordinator builder must install the shared wheel into its runtime venv."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_coordinator_builder_copies_shared_package_before_sync() -> None:
    dockerfile = (ROOT / "agent-coordinator/Dockerfile").read_text()
    package_copy = "COPY packages/openbao-credentials/ /packages/openbao-credentials/"
    assert package_copy in dockerfile
    assert dockerfile.index(package_copy) < dockerfile.index("RUN touch README.md && uv sync")


def test_coordinator_declares_noneditable_package_source() -> None:
    import tomllib

    manifest = tomllib.loads((ROOT / "agent-coordinator/pyproject.toml").read_text())
    assert "openbao-credentials" in manifest["project"]["dependencies"]
    assert manifest["tool"]["uv"]["sources"]["openbao-credentials"] == {
        "path": "../packages/openbao-credentials"
    }


def test_ci_container_smoke_imports_shared_package() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "'openbao_credentials'," in workflow
