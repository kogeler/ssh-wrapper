# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Tests for the independent package boundary."""

from __future__ import annotations

import importlib.metadata
import inspect
import re
from pathlib import Path

import pytest

import ssh_wrapper

ROOT = Path(__file__).resolve().parents[1]
API_DOCUMENT = ROOT / "docs/user/api.md"


def test_public_api_and_version_are_owned_by_this_package() -> None:
    assert (
        ssh_wrapper.__version__
        == (ROOT / ".version").read_text(encoding="utf-8").strip()
    )
    assert set(ssh_wrapper.__all__) == {
        "BoundedTail",
        "ConnectionMode",
        "ConnectionSpec",
        "ConnectionState",
        "OpenSSHMaster",
        "OwnedRemoteProcess",
        "SESSION_ENVIRONMENT_VARIABLES",
        "SSHError",
        "SSHMasterSettings",
        "__version__",
        "build_remote_supervisor_program",
        "resolve_session_environment",
    }


def test_error_without_details_has_the_minimal_stable_shape() -> None:
    error = ssh_wrapper.SSHError("connection_lost", "the master is unavailable")

    assert str(error) == "the master is unavailable"
    assert error.to_dict() == {
        "error": "connection_lost",
        "message": "the master is unavailable",
    }


def test_public_api_documentation_matches_the_exported_surface() -> None:
    documentation = API_DOCUMENT.read_text(encoding="utf-8")
    import_table = documentation.split("## Connection values", 1)[0]
    documented = re.findall(r"^\| `([^`]+)` \|", import_table, re.MULTILINE)

    assert len(documented) == len(set(documented))
    assert set(documented) == set(ssh_wrapper.__all__)
    for fragment in (
        "ConnectionSpec.from_alias(ssh_alias: str) -> ConnectionSpec",
        "ConnectionSpec.from_direct(host: str, user: str, port: int = 22)",
        'ConnectionMode` has `ALIAS = "alias"` and `DIRECT = "direct"',
        "`server_alive_interval` | `int` | `15`",
        "`server_alive_count_max` | `int` | `3`",
        '`runtime_prefix` | `str` | `"remote-ssh"`',
        "a non-empty filename prefix with",
        "runtime_base: Path | None = None",
        "tail_bytes: int = 16384",
        'BoundedTail(limit: int = 16384, data: bytes = b"")',
        "initial `data` no longer than that limit",
        "await resolve_session_environment(base_environment=None)",
    ):
        assert fragment in documentation


def _parameters(value: object) -> dict[str, inspect.Parameter]:
    return dict(inspect.signature(value).parameters)


def test_public_call_shapes_defaults_and_async_boundaries_are_stable() -> None:
    empty = inspect.Signature.empty
    positional = inspect.Parameter.POSITIONAL_OR_KEYWORD
    keyword_only = inspect.Parameter.KEYWORD_ONLY

    assert {
        name: (parameter.kind, parameter.default)
        for name, parameter in _parameters(ssh_wrapper.BoundedTail).items()
    } == {
        "limit": (positional, 16_384),
        "data": (positional, b""),
    }
    assert list(_parameters(ssh_wrapper.ConnectionSpec.from_alias)) == ["ssh_alias"]
    direct = _parameters(ssh_wrapper.ConnectionSpec.from_direct)
    assert list(direct) == ["host", "user", "port"]
    assert direct["port"].default == 22

    settings = _parameters(ssh_wrapper.SSHMasterSettings)
    assert list(settings) == [
        "ssh_path",
        "false_path",
        "connect_timeout",
        "server_alive_interval",
        "server_alive_count_max",
        "runtime_prefix",
    ]
    assert [settings[name].default for name in list(settings)[:3]] == [empty] * 3
    assert [settings[name].default for name in list(settings)[3:]] == [
        15,
        3,
        "remote-ssh",
    ]

    master = _parameters(ssh_wrapper.OpenSSHMaster)
    assert list(master) == ["settings", "connection", "runtime_base"]
    assert master["runtime_base"].kind is keyword_only
    assert master["runtime_base"].default is None

    owned = _parameters(ssh_wrapper.OwnedRemoteProcess)
    assert list(owned) == [
        "master",
        "argv",
        "heartbeat_interval",
        "lease_timeout",
        "grace_timeout",
        "tail_bytes",
    ]
    for name in ("heartbeat_interval", "lease_timeout", "grace_timeout"):
        assert owned[name].kind is keyword_only and owned[name].default is empty
    assert owned["tail_bytes"].kind is keyword_only
    assert owned["tail_bytes"].default == 16_384

    supervisor = _parameters(ssh_wrapper.build_remote_supervisor_program)
    assert list(supervisor) == ["argv", "lease_timeout", "grace_timeout"]
    assert all(
        supervisor[name].kind is keyword_only and supervisor[name].default is empty
        for name in ("lease_timeout", "grace_timeout")
    )
    assert (
        _parameters(ssh_wrapper.resolve_session_environment)["base_environment"].default
        is None
    )

    for operation in (
        ssh_wrapper.OpenSSHMaster.start,
        ssh_wrapper.OpenSSHMaster.ensure_ready,
        ssh_wrapper.OpenSSHMaster.close,
        ssh_wrapper.OwnedRemoteProcess.start,
        ssh_wrapper.OwnedRemoteProcess.wait,
        ssh_wrapper.OwnedRemoteProcess.close,
        ssh_wrapper.resolve_session_environment,
    ):
        assert inspect.iscoroutinefunction(operation)

    assert [(item.name, item.value) for item in ssh_wrapper.ConnectionMode] == [
        ("ALIAS", "alias"),
        ("DIRECT", "direct"),
    ]
    assert [(item.name, item.value) for item in ssh_wrapper.ConnectionState] == [
        ("NEW", "new"),
        ("STARTING", "starting"),
        ("READY", "ready"),
        ("LOST", "lost"),
        ("CLOSING", "closing"),
        ("CLOSED", "closed"),
    ]


def test_version_resolution_uses_installed_metadata_and_safe_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ssh_wrapper,
        "__file__",
        str(tmp_path / "installed/ssh_wrapper/__init__.py"),
    )
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "9.8.7")
    assert ssh_wrapper._resolve_version() == "9.8.7"

    def missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert ssh_wrapper._resolve_version() == "0.0.0+unknown"
