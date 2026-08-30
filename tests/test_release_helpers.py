# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Tests for PR metadata and exact publication recovery helpers."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIRECTORY = ROOT / ".github/scripts"
VERSION = "1.2.3"


def _module(name: str) -> ModuleType:
    path = SCRIPT_DIRECTORY / f"{name}.py"
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def test_pr_body_preserves_manual_text_and_replaces_only_managed_content() -> None:
    helper = _module("pr_body")
    start = helper.START_MARKER
    end = helper.END_MARKER
    existing = f"Before.\n\n{start}\n## Old\n\n- Old.\n{end}\n\nAfter.\n"
    section = helper.latest_changelog_section(
        "# Changelog\n\n## [Unreleased]\n\n## [1.2.3] - 2026-08-30\n\n- Exact.\n"
    )

    assert helper.updated_body(existing, section) == (
        f"Before.\n\n{start}\n## [1.2.3] - 2026-08-30\n\n- Exact.\n{end}\n\nAfter.\n"
    )


def _pypi_fixture(root: Path) -> tuple[Path, Path]:
    dist = root / "dist"
    dist.mkdir(parents=True)
    urls: list[dict[str, Any]] = []
    for name, package_type in (
        (f"ssh_wrapper-{VERSION}-py3-none-any.whl", "bdist_wheel"),
        (f"ssh_wrapper-{VERSION}.tar.gz", "sdist"),
    ):
        path = dist / name
        path.write_bytes(f"contents:{name}".encode())
        urls.append(
            {
                "filename": name,
                "packagetype": package_type,
                "size": path.stat().st_size,
                "digests": {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
                "yanked": False,
            }
        )
    metadata = root / "pypi.json"
    metadata.write_text(
        json.dumps({"info": {"name": "ssh-wrapper", "version": VERSION}, "urls": urls}),
        encoding="utf-8",
    )
    return dist, metadata


def _verify_pypi(dist: Path, metadata: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIRECTORY / "verify_pypi_release.py"),
            "--project",
            "ssh-wrapper",
            "--version",
            VERSION,
            "--dist-dir",
            str(dist),
            "--metadata-file",
            str(metadata),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_pypi_verifier_accepts_only_exact_local_files(tmp_path: Path) -> None:
    dist, metadata = _pypi_fixture(tmp_path)
    exact = _verify_pypi(dist, metadata)
    assert exact.returncode == 0, exact.stderr
    assert exact.stdout.count(" matches PyPI (") == 2

    (dist / f"ssh_wrapper-{VERSION}.tar.gz").write_bytes(b"conflict")
    conflict = _verify_pypi(dist, metadata)
    assert conflict.returncode == 1
    assert "does not match PyPI" in conflict.stderr

    dist, metadata = _pypi_fixture(tmp_path / "yanked")
    payload = json.loads(metadata.read_text(encoding="utf-8"))
    payload["urls"][0]["yanked"] = True
    metadata.write_text(json.dumps(payload), encoding="utf-8")
    yanked = _verify_pypi(dist, metadata)
    assert yanked.returncode == 1
    assert "is yanked" in yanked.stderr
