"""Pure SRT settings renderer and prepared-command lifecycle."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import platform as platform_module
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Iterator, Literal, Mapping, Sequence

from .checkout_policy import is_managed_execution_root

SRT_VERSION = "0.0.77"
SRT_RESOLVED = (
    "https://registry.npmjs.org/@anthropic-ai/sandbox-runtime/"
    "-/sandbox-runtime-0.0.77.tgz"
)
SRT_INTEGRITY = (
    "sha512-uOe6kkAbo91r5shXXBxZ1DKbOpWmnXkNDDujXrFJRaHSG7D7s8b7Yfsu0pGDkYFg"
    "KZ2ECtVCNisl6pCYcaMF7A=="
)
MIN_NODE_VERSION = (20, 11, 0)
BASELINE_DENIED_RESOLVED_ADDRESSES = (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "100.100.100.200/32",
    "127.0.0.0/8",
    "168.63.129.16/32",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.192/32",
    "192.168.0.0/16",
    "224.0.0.0/4",
    "::/128",
    "::1/128",
    "fc00::/7",
    "fd00:42::42/128",
    "fd00:c1::a9fe:a9fe/128",
    "fd00:ec2::/32",
    "fd20:ce::254/128",
    "fe80::/10",
    "ff00::/8",
)
_SAFE_ENV_NAMES = frozenset({"LANG", "TERM", "TZ"})
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SandboxProfileError(RuntimeError):
    """A sandbox cannot be rendered or prepared safely."""

    def __init__(self, reason: str, *, fail_open: bool = False) -> None:
        self.reason = reason
        self.fail_open = fail_open
        super().__init__(reason)


@dataclass(frozen=True)
class RuntimePaths:
    node: Path
    entrypoint: Path
    runtime_dir: Path
    primary_checkout: Path
    common_git_dir: Path
    version: str
    bwrap: Path | None
    socat: Path | None
    rg: Path | None


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    status: Literal[
        "passed",
        "unsupported_platform",
        "runtime_missing",
        "runtime_incompatible",
        "capability_failed",
    ]
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class SandboxLaunch:
    worktree_root: Path
    common_repo: Path
    common_git_dir: Path
    git_toplevel: Path
    git_common_dir: Path
    vendor_executable: Path
    vendor_install_root: Path
    policy: Mapping[str, Any]
    write_capable: bool
    credential_env_key: str
    state_env_keys: tuple[str, ...]
    credential_paths: tuple[Path, ...] = ()
    authored_read_paths: tuple[Path, ...] = ()
    allowed_tool_dirs: tuple[Path, ...] = ()
    read_only_snapshot: bool = False

    def with_policy(self, policy: Mapping[str, Any]) -> SandboxLaunch:
        return replace(self, policy=policy)


@dataclass(frozen=True)
class RenderedSettings:
    settings: dict[str, Any]
    settings_digest: str


@dataclass
class PreparedCommand:
    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    settings_path: Path
    state_root: Path
    settings_digest: str
    runtime_version: str
    cleanup_status: Literal["not_started", "succeeded", "failed"] = "not_started"
    cleanup_residual_paths: list[str] = field(default_factory=list)


def _canonical_bytes(value: Any) -> bytes:
    def reject_float(item: Any) -> None:
        if isinstance(item, float):
            raise SandboxProfileError("floating-point values are forbidden in sandbox settings")
        if isinstance(item, Mapping):
            for child in item.values():
                reject_float(child)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            for child in item:
                reject_float(child)

    reject_float(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _unique_paths(paths: Sequence[Path]) -> list[str]:
    return sorted({str(path.resolve(strict=False)) for path in paths})


def _network_entry(rule: Mapping[str, Any]) -> str:
    destination = str(rule.get("destination_pattern", ""))
    kind = rule.get("destination_kind")
    if kind not in {"dns", "ipv4", "ipv6"} or not destination:
        raise SandboxProfileError("invalid typed network destination")
    port = rule.get("port")
    if port is not None and (type(port) is not int or not 1 <= port <= 65535):
        raise SandboxProfileError("invalid network destination port")
    if kind in {"ipv4", "ipv6"}:
        literal = (
            destination[1:-1] if kind == "ipv6" and destination.startswith("[") else destination
        )
        try:
            address = ipaddress.ip_address(literal)
        except ValueError as exc:
            raise SandboxProfileError("invalid IP literal") from exc
        if rule.get("action") == "allow" and (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise SandboxProfileError("private IP literal allow is not renderable")
    return f"{destination}:{port}" if port is not None else destination


def render_sandbox_settings(
    launch: SandboxLaunch,
    *,
    state_root: Path,
    platform: str | None = None,
    runtime_read_paths: Sequence[Path] = (),
) -> RenderedSettings:
    """Render deterministic, conservative SRT settings without side effects."""

    policy = launch.policy
    if policy.get("schema_version") != 1 or policy.get("default_action") != "deny":
        raise SandboxProfileError("sandbox requires a version-1 default-deny policy")
    rules = policy.get("rules")
    if not isinstance(rules, list):
        raise SandboxProfileError("sandbox policy rules must be a list")
    allowed: list[str] = []
    denied: list[str] = []
    for rule in rules:
        if not isinstance(rule, Mapping):
            raise SandboxProfileError("sandbox policy rule must be an object")
        entry = _network_entry(rule)
        action = rule.get("action")
        if action == "allow":
            allowed.append(entry)
        elif action == "deny":
            denied.append(entry)
        else:
            raise SandboxProfileError("sandbox policy action must be allow or deny")

    resolved_root = launch.worktree_root.resolve(strict=False)
    resolved_git = launch.common_git_dir.resolve(strict=False)
    resolved_state = state_root.resolve(strict=False)
    resolved_vendor = launch.vendor_executable.resolve(strict=False)
    resolved_install = launch.vendor_install_root.resolve(strict=False)
    platform = platform or ("darwin" if platform_module.system() == "Darwin" else "linux")
    home_region = Path("/Users" if platform == "darwin" else "/home")
    credential_paths = tuple(path.resolve(strict=False) for path in launch.credential_paths)
    allow_read = _unique_paths(
        (
            resolved_root,
            resolved_git,
            resolved_state,
            resolved_vendor,
            resolved_install,
            *runtime_read_paths,
            *launch.authored_read_paths,
        )
    )
    deny_read = _unique_paths((home_region, *credential_paths))
    allow_write_paths = [resolved_state]
    if launch.write_capable:
        allow_write_paths.append(resolved_root)
    deny_write = _unique_paths((resolved_git, resolved_root / ".git", *credential_paths))
    settings: dict[str, Any] = {
        "filesystem": {
            "denyRead": deny_read,
            "allowRead": allow_read,
            "allowWrite": _unique_paths(tuple(allow_write_paths)),
            "denyWrite": deny_write,
        },
        "network": {
            "allowedDomains": allowed,
            "deniedDomains": denied,
            "deniedResolvedAddresses": list(BASELINE_DENIED_RESOLVED_ADDRESSES),
            "allowUnixSockets": [],
            "allowAllUnixSockets": False,
            "allowLocalBinding": False,
        },
        "enableWeakerNestedSandbox": False,
        "enableWeakerNetworkIsolation": False,
        "allowAppleEvents": False,
    }
    digest = hashlib.sha256(_canonical_bytes(settings)).hexdigest()
    return RenderedSettings(settings=settings, settings_digest=digest)


def build_child_environment(
    *,
    parent_env: Mapping[str, str],
    state_root: Path,
    runtime: RuntimePaths,
    vendor_executable: Path,
    credential_env_key: str,
    state_env_keys: Sequence[str],
    allowed_tool_dirs: Sequence[Path],
) -> dict[str, str]:
    """Build a positive child allowlist; never copy the coordinator environment."""

    if not _ENV_NAME.fullmatch(credential_env_key):
        raise SandboxProfileError("invalid credential environment key")
    if credential_env_key not in parent_env or not parent_env[credential_env_key]:
        raise SandboxProfileError("selected sandbox credential is unavailable")
    env = {
        key: value
        for key, value in parent_env.items()
        if key in _SAFE_ENV_NAMES or key.startswith("LC_")
    }
    home = state_root / "home"
    tmp = state_root / "tmp"
    xdg = state_root / "xdg"
    for path in (home, tmp, xdg / "config", xdg / "cache", xdg / "state"):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(xdg / "config"),
            "XDG_CACHE_HOME": str(xdg / "cache"),
            "XDG_STATE_HOME": str(xdg / "state"),
            "TMPDIR": str(tmp),
            "TEMP": str(tmp),
            "TMP": str(tmp),
            "GIT_OPTIONAL_LOCKS": "0",
            credential_env_key: parent_env[credential_env_key],
        }
    )
    for key in state_env_keys:
        if not _ENV_NAME.fullmatch(key):
            raise SandboxProfileError(f"invalid state environment key: {key}")
        if key in env or state_env_keys.count(key) != 1:
            raise SandboxProfileError(f"duplicate or reserved state environment key: {key}")
        target = state_root / "vendor-state" / key.lower()
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        env[key] = str(target)
    path_dirs = {
        runtime.node.parent.resolve(),
        runtime.entrypoint.parent.resolve(),
        vendor_executable.resolve().parent,
        *(path.resolve() for path in allowed_tool_dirs),
    }
    for candidate in (Path("/usr/bin"), Path("/bin"), Path("/usr/sbin"), Path("/sbin")):
        if candidate.is_dir() and not os.access(candidate, os.W_OK):
            path_dirs.add(candidate)
    env["PATH"] = os.pathsep.join(sorted(str(path) for path in path_dirs))
    return env


def _read_json(path: Path, reason: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SandboxProfileError(reason, fail_open=True) from exc
    if not isinstance(value, dict):
        raise SandboxProfileError(reason, fail_open=True)
    return value


def discover_sandbox_runtime(
    cwd: Path,
    *,
    runtime_override: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
    git_runner: Callable[..., Any] = subprocess.run,
) -> RuntimePaths:
    """Discover the one pinned installation through Git's common directory."""

    def git_value(flag: str) -> Path:
        try:
            result = git_runner(
                ["git", "rev-parse", flag],
                cwd=str(cwd),
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise SandboxProfileError("git_runtime_discovery_failed", fail_open=True) from exc
        raw = result.stdout.strip()
        path = Path(raw)
        return (cwd / path).resolve() if not path.is_absolute() else path.resolve()

    toplevel = git_value("--show-toplevel")
    common_git = git_value("--git-common-dir")
    primary = common_git.parent if common_git.name == ".git" else toplevel
    if runtime_override is not None and not runtime_override.is_absolute():
        raise SandboxProfileError("runtime_override_must_be_absolute", fail_open=True)
    runtime_dir = (runtime_override or (primary / "tools" / "sandbox-runtime")).resolve()
    lock = _read_json(runtime_dir / "package-lock.json", "runtime_lock_missing")
    package_path = runtime_dir / "node_modules" / "@anthropic-ai" / "sandbox-runtime"
    package = _read_json(package_path / "package.json", "runtime_package_missing")
    locked = lock.get("packages", {}).get("node_modules/@anthropic-ai/sandbox-runtime", {})
    if (
        package.get("version") != SRT_VERSION
        or locked.get("version") != SRT_VERSION
        or locked.get("resolved") != SRT_RESOLVED
        or locked.get("integrity") != SRT_INTEGRITY
    ):
        raise SandboxProfileError("runtime_version_or_integrity_mismatch", fail_open=True)
    bin_value = package.get("bin", {}).get("srt") if isinstance(package.get("bin"), dict) else None
    if not isinstance(bin_value, str):
        raise SandboxProfileError("runtime_entrypoint_missing", fail_open=True)
    entrypoint = (package_path / bin_value).resolve()
    node_value = which("node")
    if not node_value or not entrypoint.is_file():
        raise SandboxProfileError("runtime_executable_missing", fail_open=True)
    return RuntimePaths(
        node=Path(node_value).resolve(),
        entrypoint=entrypoint,
        runtime_dir=runtime_dir,
        primary_checkout=primary,
        common_git_dir=common_git,
        version=SRT_VERSION,
        bwrap=Path(value).resolve() if (value := which("bwrap")) else None,
        socat=Path(value).resolve() if (value := which("socat")) else None,
        rg=Path(value).resolve() if (value := which("rg")) else None,
    )


def preflight_runtime(
    runtime: RuntimePaths,
    *,
    platform: str | None = None,
    run_probe: bool = True,
    runner: Callable[..., Any] = subprocess.run,
) -> PreflightResult:
    """Prove runtime prerequisites, returning exact unavailable capabilities."""

    platform = platform or ("darwin" if platform_module.system() == "Darwin" else "linux")
    if platform not in {"linux", "darwin"}:
        return PreflightResult(False, "unsupported_platform", (f"platform:{platform}",))
    missing: list[str] = []
    for name in ("node", "entrypoint"):
        path = getattr(runtime, name)
        if not path.is_file():
            missing.append(name)
    if missing:
        return PreflightResult(False, "runtime_missing", tuple(sorted(set(missing))))
    if runtime.version != SRT_VERSION:
        return PreflightResult(False, "runtime_incompatible", (f"srt:{runtime.version}",))
    if platform == "linux":
        for name in ("bwrap", "socat", "rg"):
            path = getattr(runtime, name)
            if path is None or not path.is_file():
                missing.append(name)
        if platform_module.machine().lower() not in {"x86_64", "amd64", "aarch64", "arm64"}:
            missing.append(f"seccomp_arch:{platform_module.machine()}")
        userns = Path("/proc/sys/kernel/unprivileged_userns_clone")
        if userns.exists() and userns.read_text().strip() != "1":
            missing.append("unprivileged_userns")
        apparmor = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
        if apparmor.exists() and apparmor.read_text().strip() == "1":
            missing.append("apparmor_restrict_unprivileged_userns")
    elif not Path("/usr/bin/sandbox-exec").is_file():
        missing.append("sandbox-exec")
    if missing:
        return PreflightResult(False, "capability_failed", tuple(sorted(set(missing))))
    if not run_probe:
        return PreflightResult(True, "passed")
    try:
        version = (
            runner(
                [str(runtime.node), "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            .stdout.strip()
            .lstrip("v")
        )
        parsed = tuple(int(piece) for piece in version.split(".")[:3])
        if parsed < MIN_NODE_VERSION:
            return PreflightResult(False, "runtime_incompatible", (f"node:{version}",))
        with tempfile.TemporaryDirectory(prefix="act-srt-probe-") as temp:
            settings = Path(temp) / "settings.json"
            settings.write_text(
                json.dumps(
                    {
                        "filesystem": {
                            "denyRead": [],
                            "allowRead": [],
                            "allowWrite": [temp],
                            "denyWrite": [],
                        },
                        "network": {"allowedDomains": [], "deniedDomains": []},
                    }
                )
            )
            os.chmod(settings, 0o600)
            completed = runner(
                [
                    str(runtime.node),
                    str(runtime.entrypoint),
                    "--settings",
                    str(settings),
                    "--",
                    "/usr/bin/true",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        if completed.returncode != 0:
            detail = (
                (completed.stderr or completed.stdout or "probe_failed").strip().splitlines()[-1]
            )
            return PreflightResult(False, "capability_failed", (f"srt_probe:{detail[:160]}",))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return PreflightResult(False, "capability_failed", (f"srt_probe:{type(exc).__name__}",))
    return PreflightResult(True, "passed")


@contextmanager
def prepare_sandbox_command(
    *,
    runtime: RuntimePaths,
    launch: SandboxLaunch,
    vendor_argv: Sequence[str],
    parent_env: Mapping[str, str],
    temp_parent: Path | None = None,
    skip_preflight: bool = False,
) -> Iterator[PreparedCommand]:
    """Validate, materialize, and clean one unique sandbox launch."""

    if not is_managed_execution_root(
        launch.worktree_root,
        launch.common_repo,
        git_toplevel=launch.git_toplevel,
        git_common_dir=launch.git_common_dir,
        read_only=launch.read_only_snapshot,
    ):
        raise SandboxProfileError("unsafe_execution_root")
    executable = launch.vendor_executable.resolve(strict=True)
    install_root = launch.vendor_install_root.resolve(strict=True)
    try:
        executable.relative_to(install_root)
    except ValueError as exc:
        raise SandboxProfileError("vendor executable escapes install root") from exc
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise SandboxProfileError("vendor executable is not executable")
    if not os.access(executable, os.R_OK) or not os.access(install_root, os.R_OK | os.X_OK):
        raise SandboxProfileError("vendor executable or install root is unreadable")
    resolved_worktree = launch.worktree_root.resolve()
    for tool_dir in launch.allowed_tool_dirs:
        resolved_tool = tool_dir.resolve(strict=True)
        try:
            resolved_tool.relative_to(resolved_worktree)
        except ValueError as exc:
            raise SandboxProfileError("configured tool directory escapes worktree") from exc
    if not skip_preflight:
        preflight = preflight_runtime(runtime)
        if not preflight.ok:
            raise SandboxProfileError(
                f"{preflight.status}: {', '.join(preflight.missing)}",
                fail_open=True,
            )
    parent = (temp_parent or Path(tempfile.gettempdir())).resolve(strict=True)
    for forbidden in (Path.home().resolve(), launch.common_repo.resolve()):
        if parent == forbidden or forbidden in parent.parents:
            raise SandboxProfileError("sandbox state parent is inside a protected root")
    state_root = Path(tempfile.mkdtemp(prefix="act-sandbox-", dir=parent))
    os.chmod(state_root, 0o700)
    runtime_reads = tuple(
        path
        for path in (
            runtime.runtime_dir,
            runtime.node,
            runtime.entrypoint,
            runtime.bwrap,
            runtime.socat,
            runtime.rg,
        )
        if path is not None
    )
    prepared: PreparedCommand | None = None
    try:
        rendered = render_sandbox_settings(
            launch,
            state_root=state_root,
            runtime_read_paths=runtime_reads,
        )
        settings_path = state_root / "settings.json"
        fd = os.open(
            settings_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical_bytes(rendered.settings))
            stream.flush()
            os.fsync(stream.fileno())
        env = build_child_environment(
            parent_env=parent_env,
            state_root=state_root,
            runtime=runtime,
            vendor_executable=executable,
            credential_env_key=launch.credential_env_key,
            state_env_keys=launch.state_env_keys,
            allowed_tool_dirs=launch.allowed_tool_dirs,
        )
        argv = (
            str(runtime.node),
            str(runtime.entrypoint),
            "--settings",
            str(settings_path),
            "--",
            str(executable),
            *(str(value) for value in vendor_argv),
        )
        prepared = PreparedCommand(
            argv=argv,
            env=env,
            cwd=launch.worktree_root.resolve(),
            settings_path=settings_path,
            state_root=state_root,
            settings_digest=rendered.settings_digest,
            runtime_version=runtime.version,
        )
        yield prepared
    finally:
        try:
            shutil.rmtree(state_root)
            if prepared is not None:
                prepared.cleanup_status = "succeeded"
        except OSError:
            if prepared is not None:
                prepared.cleanup_status = "failed"
                prepared.cleanup_residual_paths = [str(state_root)]
