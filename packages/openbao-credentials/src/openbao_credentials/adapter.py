"""Typed, fail-closed OpenBao credential access and one-use bootstrap reuse."""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

import hvac
import requests.exceptions

_ROLE = re.compile(r"^(agent|service)-[a-z][a-z0-9-]*$")
_MOUNT = re.compile(r"^[a-z][a-z0-9-]*$")
_LOGICAL = re.compile(r"^(agents|vendors)/[a-z][a-z0-9-]*$")
_PRINCIPAL = re.compile(r"^spiffe://coordinator\.rotkohl\.ai/(agent|service)/[a-z][a-z0-9-]*$")


class ErrorCode(StrEnum):
    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"
    BOOTSTRAP_INVALID = "BOOTSTRAP_INVALID"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    SECRET_NOT_FOUND = "SECRET_NOT_FOUND"
    SECRET_MALFORMED = "SECRET_MALFORMED"
    TIMEOUT = "TIMEOUT"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"


class BaoCredentialError(RuntimeError):
    """Sanitized failure; callers may log ``code`` and ``category`` only."""

    def __init__(self, code: ErrorCode, category: str = "credential") -> None:
        self.code = code
        self.category = category
        super().__init__(f"OpenBao {category}: {code.value}")


@dataclass(frozen=True)
class PrincipalOpenBaoConfig:
    addr: str
    mount: str = "secret"
    bootstrap_dir: Path | None = None
    timeout: float = 5.0

    @classmethod
    def from_env(cls) -> PrincipalOpenBaoConfig:
        addr = os.environ.get("BAO_ADDR", "")
        directory = os.environ.get("BAO_BOOTSTRAP_DIR", "")
        if not addr or not directory:
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "configuration")
        try:
            timeout = float(os.environ.get("BAO_TIMEOUT", "5"))
        except ValueError:
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "configuration") from None
        return cls(
            addr=addr,
            mount=os.environ.get("BAO_MOUNT_PATH", "secret"),
            bootstrap_dir=Path(directory),
            timeout=timeout,
        )

    def validate(self) -> None:
        if not self.addr or not self.addr.startswith(("http://", "https://")):
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "configuration")
        if not _MOUNT.fullmatch(self.mount) or self.timeout <= 0:
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "configuration")


@dataclass(frozen=True)
class BootstrapPaths:
    bundle: Path
    session: Path
    lock: Path


def bootstrap_paths(directory: Path, role_name: str) -> BootstrapPaths:
    if not _ROLE.fullmatch(role_name):
        raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "bootstrap")
    return BootstrapPaths(
        bundle=directory / f"{role_name}.bundle.json",
        session=directory / f"{role_name}.session.json",
        lock=directory / f"{role_name}.lock",
    )


@dataclass(frozen=True)
class Session:
    principal_id: str
    client_token: str = field(repr=False)
    renewable: bool
    period_seconds: int
    lease_expires_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "principal_id": self.principal_id,
            "client_token": self.client_token,
            "renewable": self.renewable,
            "period_seconds": self.period_seconds,
            "lease_expires_at": self.lease_expires_at.isoformat(),
        }


@dataclass(frozen=True)
class SecretPayload:
    """The only allowed KV-v2 data payload for an agent or vendor path."""

    api_key: str = field(repr=False)


def _datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("invalid timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("missing timezone")
    return parsed.astimezone(UTC)


def _regular_private(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600


def _read_private_json(path: Path, category: str) -> dict[str, Any]:
    try:
        if not _regular_private(path):
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, category)
        flags = os.O_RDONLY | os.O_NOFOLLOW
        with os.fdopen(os.open(path, flags), "r", encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError("not object")
        return value
    except FileNotFoundError:
        raise BaoCredentialError(ErrorCode.BOOTSTRAP_INVALID, category) from None
    except (OSError, ValueError, TypeError):
        raise BaoCredentialError(ErrorCode.BOOTSTRAP_INVALID, category) from None


def _atomic_private_json(path: Path, value: dict[str, Any]) -> None:
    if path.is_symlink():
        raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "session")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _classify(exc: Exception, *, auth: bool = False) -> BaoCredentialError:
    if isinstance(exc, BaoCredentialError):
        return exc
    if isinstance(exc, hvac.exceptions.Forbidden):
        return BaoCredentialError(ErrorCode.AUTHORIZATION_DENIED)
    if isinstance(exc, hvac.exceptions.InvalidPath):
        return BaoCredentialError(ErrorCode.SECRET_NOT_FOUND)
    if isinstance(exc, hvac.exceptions.Unauthorized):
        return BaoCredentialError(ErrorCode.AUTHENTICATION_FAILED if auth else ErrorCode.TOKEN_EXPIRED)
    if isinstance(exc, (TimeoutError, requests.exceptions.Timeout)):
        return BaoCredentialError(ErrorCode.TIMEOUT)
    return BaoCredentialError(ErrorCode.BACKEND_UNAVAILABLE)


class OpenBaoClient:
    """Typed operations over hvac; raw API dictionaries stay in this module."""

    def __init__(self, config: PrincipalOpenBaoConfig, *, client: Any = None) -> None:
        config.validate()
        self.config = config
        self.client = client if client is not None else hvac.Client(url=config.addr, timeout=config.timeout)

    def _paths(self, role_name: str) -> BootstrapPaths:
        directory = self.config.bootstrap_dir
        if directory is None:
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "bootstrap")
        try:
            info = directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
                or info.st_uid != os.geteuid()):
                raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "bootstrap")
        except OSError:
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "bootstrap") from None
        return bootstrap_paths(directory, role_name)

    def verify_kv_v2_mount(self) -> None:
        """Preflight the configured mount using a provisioner-capable token."""
        try:
            response = self.client.sys.list_mounted_secrets_engines()
            mounts = response.get("data", response)
            mounted = mounts.get(f"{self.config.mount}/")
            if (not isinstance(mounted, dict) or mounted.get("type") != "kv"
                or mounted.get("options", {}).get("version") != "2"):
                raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "mount")
        except BaoCredentialError:
            raise
        except Exception as exc:
            raise _classify(exc) from None

    def read_secret(self, logical_path: str) -> SecretPayload:
        """Read one exact KV-v2 agent/vendor payload at a mount-relative path."""
        if not _LOGICAL.fullmatch(logical_path):
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "path")
        try:
            response = self.client.secrets.kv.v2.read_secret_version(
                path=logical_path, mount_point=self.config.mount
            )
        except Exception as exc:
            raise _classify(exc) from None
        try:
            payload = response["data"]["data"]
            if set(payload) != {"api_key"} or not isinstance(payload["api_key"], str) or not payload["api_key"]:
                raise ValueError("invalid payload")
            return SecretPayload(api_key=payload["api_key"])
        except (KeyError, TypeError, ValueError):
            raise BaoCredentialError(ErrorCode.SECRET_MALFORMED, "credential") from None

    def read_api_key(self, logical_path: str) -> str:
        return self.read_secret(logical_path).api_key

    def read_agent_secret(self, name: str) -> SecretPayload:
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", name):
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "path")
        return self.read_secret(f"agents/{name}")

    def read_vendor_secret(self, vendor_id: str) -> SecretPayload:
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", vendor_id):
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "path")
        return self.read_secret(f"vendors/{vendor_id}")

    def read_agent_key(self, name: str) -> str:
        return self.read_agent_secret(name).api_key

    def read_vendor_key(self, vendor_id: str) -> str:
        return self.read_vendor_secret(vendor_id).api_key

    def ensure_session(self, principal_id: str, role_name: str) -> Session:
        """Serialize first unwrap/renewal across processes and reuse valid tokens."""
        if not _PRINCIPAL.fullmatch(principal_id):
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "principal")
        paths = self._paths(role_name)
        try:
            lock_fd = os.open(paths.lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            if not _regular_private(paths.lock):
                os.close(lock_fd)
                raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "session")
        except OSError:
            raise BaoCredentialError(ErrorCode.CONFIGURATION_INVALID, "session") from None
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            if paths.session.exists() or paths.session.is_symlink():
                session = self._load_session(paths.session, principal_id)
                if session.lease_expires_at <= datetime.now(UTC):
                    raise BaoCredentialError(ErrorCode.TOKEN_EXPIRED, "session")
                if session.lease_expires_at <= datetime.now(UTC) + timedelta(seconds=60):
                    session = self._renew(session)
                    _atomic_private_json(paths.session, session.to_dict())
                self.client.token = session.client_token
                return session
            session = self._bootstrap(paths.bundle, principal_id, role_name)
            _atomic_private_json(paths.session, session.to_dict())
            self.client.token = session.client_token
            return session
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def _load_session(self, path: Path, principal_id: str) -> Session:
        value = _read_private_json(path, "session")
        try:
            if (value.get("version") != 1 or value.get("principal_id") != principal_id
                or value.get("renewable") is not True or set(value) != {
                    "version", "principal_id", "client_token", "renewable", "period_seconds", "lease_expires_at"
                }):
                raise ValueError("invalid session")
            token = value["client_token"]
            period = value["period_seconds"]
            if not isinstance(token, str) or not token or not isinstance(period, int) or period < 1:
                raise ValueError("invalid session")
            return Session(principal_id, token, True, period, _datetime(value["lease_expires_at"]))
        except (ValueError, KeyError, TypeError):
            raise BaoCredentialError(ErrorCode.BOOTSTRAP_INVALID, "session") from None

    def _bootstrap(self, path: Path, principal_id: str, role_name: str) -> Session:
        bundle = _read_private_json(path, "bootstrap")
        try:
            wrapped = bundle["wrapped_secret_id"]
            expected_path = f"auth/approle/role/{role_name}/secret-id"
            if (set(bundle) != {"version", "principal_id", "role_name", "role_id", "wrapped_secret_id"}
                or set(wrapped) != {"token", "creation_path", "creation_time", "ttl_seconds"}
                or bundle.get("version") != 1 or bundle.get("principal_id") != principal_id
                or bundle.get("role_name") != role_name or not isinstance(bundle.get("role_id"), str)
                or not bundle["role_id"] or not isinstance(wrapped, dict)
                or wrapped.get("creation_path") != expected_path
                or not isinstance(wrapped.get("token"), str) or not wrapped["token"]
                or not isinstance(wrapped.get("ttl_seconds"), int)
                or wrapped["ttl_seconds"] < 1
                or _datetime(wrapped["creation_time"]) + timedelta(seconds=wrapped["ttl_seconds"]) <= datetime.now(UTC)):
                raise ValueError("invalid bundle")
        except (KeyError, TypeError, ValueError):
            raise BaoCredentialError(ErrorCode.BOOTSTRAP_INVALID, "bootstrap") from None
        try:
            lookup = self.client.adapter.post(
                "/v1/sys/wrapping/lookup", json={"token": wrapped["token"]}
            )
            server_path = lookup.get("data", {}).get("creation_path")
            if server_path != expected_path:
                raise BaoCredentialError(ErrorCode.BOOTSTRAP_INVALID, "bootstrap")
            unwrapped = self.client.sys.unwrap(token=wrapped["token"])
            secret_id = unwrapped["data"]["secret_id"]
            if not isinstance(secret_id, str) or not secret_id:
                raise BaoCredentialError(ErrorCode.BOOTSTRAP_INVALID, "bootstrap")
            login = self.client.auth.approle.login(role_id=bundle["role_id"], secret_id=secret_id)
            auth = login["auth"]
            token = auth["client_token"]
            period = auth["lease_duration"]
            if (not isinstance(token, str) or not token or auth.get("renewable") is not True
                or not isinstance(period, int) or period < 1):
                raise BaoCredentialError(ErrorCode.AUTHENTICATION_FAILED, "bootstrap")
            return Session(
                principal_id=principal_id, client_token=token, renewable=True,
                period_seconds=period,
                lease_expires_at=datetime.now(UTC) + timedelta(seconds=period),
            )
        except BaoCredentialError:
            raise
        except (KeyError, TypeError, ValueError):
            raise BaoCredentialError(ErrorCode.BOOTSTRAP_INVALID, "bootstrap") from None
        except Exception as exc:
            raise _classify(exc, auth=True) from None

    def _renew(self, session: Session) -> Session:
        self.client.token = session.client_token
        try:
            response = self.client.auth.token.renew_self()
            auth = response["auth"]
            period = auth["lease_duration"]
            if not isinstance(period, int) or period < 1 or auth.get("renewable") is not True:
                raise BaoCredentialError(ErrorCode.TOKEN_EXPIRED, "session")
            token = auth.get("client_token") or session.client_token
            return Session(session.principal_id, token, True, period, datetime.now(UTC) + timedelta(seconds=period))
        except BaoCredentialError:
            raise
        except Exception:
            raise BaoCredentialError(ErrorCode.TOKEN_EXPIRED, "session") from None
