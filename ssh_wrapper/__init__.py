# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Public API for native OpenSSH lifecycle and remote-process ownership."""

from __future__ import annotations


def _resolve_version() -> str:
    """Resolve the source-tree or installed distribution version."""
    try:
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        if (root / "pyproject.toml").is_file():
            return (root / ".version").read_text(encoding="utf-8").strip()
    except OSError:
        pass

    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("ssh-wrapper")
    except PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = _resolve_version()

from .bounded import BoundedTail
from .connection import (
    ConnectionMode,
    ConnectionSpec,
    ConnectionState,
    OpenSSHMaster,
    SSHMasterSettings,
)
from .errors import SSHError
from .remote_process import OwnedRemoteProcess, build_remote_supervisor_program
from .session_environment import (
    SESSION_ENVIRONMENT_VARIABLES,
    resolve_session_environment,
)

__all__ = [
    "SESSION_ENVIRONMENT_VARIABLES",
    "BoundedTail",
    "ConnectionMode",
    "ConnectionSpec",
    "ConnectionState",
    "OpenSSHMaster",
    "OwnedRemoteProcess",
    "SSHError",
    "SSHMasterSettings",
    "__version__",
    "build_remote_supervisor_program",
    "resolve_session_environment",
]
