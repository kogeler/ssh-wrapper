# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Machine, user, and interpreter isolation for development environments."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import machine

ROOT = Path(__file__).resolve().parents[1]


def test_environment_namespace_is_stable_private_and_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = tmp_path / "machine-id"
    monkeypatch.setattr(machine, "MACHINE_ID_FILE", identity)
    monkeypatch.setattr(machine.os, "getuid", lambda: 1000)
    raw = "0123456789abcdef" * 2
    identity.write_text(raw + "\n", encoding="ascii")
    first = machine.environment_key()
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert raw not in first
    identity.write_text(raw, encoding="ascii")
    assert machine.environment_key() == first
    identity.write_text("fedcba9876543210" * 2, encoding="ascii")
    assert machine.environment_key() != first
    identity.write_text(raw, encoding="ascii")
    monkeypatch.setattr(machine.os, "getuid", lambda: 1001)
    assert machine.environment_key() != first
    monkeypatch.setattr(machine.sys, "version_info", SimpleNamespace(major=3, minor=13))
    python313 = machine.repository_venv_root()
    monkeypatch.setattr(machine.sys, "version_info", SimpleNamespace(major=3, minor=14))
    python314 = machine.repository_venv_root()
    assert (
        python313.parent
        == python314.parent
        == Path(".venvs") / machine.environment_key()
    )
    assert python313.name == "cpython-3.13"
    assert python314.name == "cpython-3.14"


@pytest.mark.parametrize(
    "value",
    (
        b"",
        b"uninitialized\n",
        b"0" * 32,
        b"0" * 32 + b"\n",
        b"A" * 32,
        b"g" * 32,
        b"1" * 31,
        b"1" * 33,
        b"1" * 32 + b"\n\n",
        b"1" * 32 + b"\x00",
        b"1" * 1000,
    ),
)
def test_invalid_identity_has_no_common_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: bytes
) -> None:
    identity = tmp_path / "machine-id"
    identity.write_bytes(value)
    monkeypatch.setattr(machine, "MACHINE_ID_FILE", identity)
    with pytest.raises(machine.MachineIdentityError, match="invalid or uninitialized"):
        machine.repository_venv_root()


def test_machine_selector_reports_failure_without_identity_or_path_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    identity = tmp_path / "missing"
    monkeypatch.setattr(machine, "MACHINE_ID_FILE", identity)
    assert machine.main() == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "cannot read /etc/machine-id" in captured.err
    assert str(tmp_path) not in captured.err
    identity.write_text("0123456789abcdef" * 2, encoding="ascii")
    assert machine.main() == 0
    captured = capsys.readouterr()
    assert captured.out == f"{machine.repository_venv_root()}\n"
    assert not captured.err


def test_make_scopes_every_environment_and_preserves_other_owners(
    tmp_path: Path,
) -> None:
    shutil.copy2(ROOT / "Makefile", tmp_path / "Makefile")
    (tmp_path / "tools").mkdir()
    shutil.copy2(ROOT / "tools/machine.py", tmp_path / "tools/machine.py")
    shutil.copy2(
        ROOT / "tools/dependency_policy.py", tmp_path / "tools/dependency_policy.py"
    )
    shutil.copy2(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    selected = machine.repository_venv_root()
    owned = [
        tmp_path / selected / audience
        for audience in ("dev", "test", "package", "docs", "lock")
    ]
    preserved = [
        tmp_path / ".venv",
        tmp_path / ".venv-dev",
        tmp_path / ".venv-lock",
        tmp_path / ".venvs" / ("f" * 64) / "cpython-3.14" / "dev",
        tmp_path / selected.parent / "cpython-3.99" / "test",
    ]
    for path in (*owned, *preserved):
        path.mkdir(parents=True)
        (path / "sentinel").write_text("keep", encoding="ascii")
    for audience in ("dev", "test", "package", "docs"):
        (tmp_path / f"requirements-{audience}.txt").touch()
    dry_run = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "-n",
            "venv-dev",
            "venv-test",
            "venv-package",
            "venv-docs",
            "venv-lock",
            f"PY={sys.executable}",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    for path in owned:
        assert f'-m venv "{path.relative_to(tmp_path)}"' in dry_run.stdout
    cleaned = subprocess.run(
        ["make", "--no-print-directory", "clean", f"PY={sys.executable}"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert cleaned.returncode == 0, cleaned.stderr
    assert all(not path.exists() for path in owned)
    assert all(
        (path / "sentinel").read_text(encoding="ascii") == "keep" for path in preserved
    )


def test_make_rejects_failed_namespace_selection(tmp_path: Path) -> None:
    shutil.copy2(ROOT / "Makefile", tmp_path / "Makefile")
    completed = subprocess.run(
        ["make", "--no-print-directory", "-n", "clean", "PY=false"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "Cannot select machine-specific environments" in completed.stderr
    assert not completed.stdout
