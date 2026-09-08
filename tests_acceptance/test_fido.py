# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Operator-assisted FIDO acceptance, never selected by automatic CI gates."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tests_acceptance.test_openssh_acceptance import _exercise_openssh

pytestmark = [
    pytest.mark.fido,
    pytest.mark.skipif(sys.platform != "linux", reason="FIDO acceptance is Linux-only"),
]


@pytest.mark.asyncio
async def test_real_fido_one_auth_mux_and_owned_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = os.environ.get("FIDO_IDENTITY")
    if not value:
        pytest.fail(
            "Set FIDO_IDENTITY to an existing OpenSSH FIDO identity; its .pub file is required. Run only when the operator is ready to approve the native prompt.",
            pytrace=False,
        )
    identity = Path(value).expanduser().resolve(strict=True)
    if not identity.is_file() or not Path(f"{identity}.pub").is_file():
        pytest.fail("FIDO_IDENTITY and its .pub file must exist", pytrace=False)
    await _exercise_openssh(tmp_path, monkeypatch, fido_identity=identity)
    print(
        "FIDO: one authentication, mux reuse, owned cleanup, and no fallback passed.",
        flush=True,
    )
