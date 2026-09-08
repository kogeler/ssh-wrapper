# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Select checkout environments before any Python tool audience is installed."""

from __future__ import annotations

import hmac
import os
import re
import sys
from pathlib import Path

MACHINE_ID_FILE = Path("/etc/machine-id")


class MachineIdentityError(RuntimeError):
    """A valid local OS identity is unavailable."""


def environment_key() -> str:
    """Hash the machine ID and UID in the project's own namespace."""
    try:
        with MACHINE_ID_FILE.open("rb") as stream:
            value = stream.read(34)
    except OSError as error:
        raise MachineIdentityError(
            "cannot read /etc/machine-id; a valid OS machine ID is required"
        ) from error
    if re.fullmatch(rb"[0-9a-f]{32}\n?", value) is None or int(value, 16) == 0:
        raise MachineIdentityError(
            "/etc/machine-id is invalid or uninitialized; no shared venv fallback is allowed"
        )
    identity = bytes.fromhex(value.decode("ascii").strip())
    return hmac.digest(
        b"ssh-wrapper/venv-namespace/v1",
        identity + b"\0" + str(os.getuid()).encode("ascii"),
        "sha256",
    ).hex()


def repository_venv_root() -> Path:
    """Separate machines, users, and supported Python minors in a shared checkout."""
    interpreter = (
        f"{sys.implementation.name}-{sys.version_info.major}.{sys.version_info.minor}"
    )
    return Path(".venvs") / environment_key() / interpreter


def main() -> int:
    """Print the relative root using isolated Python and only its standard library."""
    try:
        print(repository_venv_root())
    except MachineIdentityError as error:
        print(f"ssh-wrapper: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
