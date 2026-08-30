# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Tests for the independent local governance surface."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_make_exposes_every_governance_boundary() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = {
        "lock",
        "refresh-dependencies",
        "freeze-check",
        "lock-platform-check",
        "dependency-validate",
        "dependency-snapshot",
        "audit",
        "format-check",
        "test-full",
        "version-check",
        "release-notes",
        "package",
        "smoke",
        "reproducibility",
        "docs-build",
        "docs-audit",
        "validate-actions",
        "test-acceptance",
        "check",
        "ci",
        "clean",
    }
    for target in targets:
        assert re.search(rf"^{re.escape(target)}:", makefile, re.MULTILINE), target
    assert not re.search(r"^version-sync:", makefile, re.MULTILINE)
    assert makefile.count("--require-hashes") >= 5
    assert makefile.count("--only-binary=:all:") >= 5
    assert "SUPPORTED_PYTHONS := 3.13 3.14" in makefile
    assert '--python-version "$$python_version" --abi "$$abi"' in makefile
    assert "check-lock-python: check-python" in makefile
    assert "CPython 3.14 is required to generate locks" in makefile
    assert "--network=none" in makefile
    assert "--read-only" in makefile and "--cap-drop=all" in makefile
    assert "tools/build_distributions.py" in makefile
    assert "tools/normalize_sdist.py" not in makefile
    assert "tools/version.py notes --repository kogeler/ssh-wrapper" in makefile
    assert not re.search(r"^venv:", makefile, re.MULTILINE)
    assert "--editable ." not in makefile
    assert "VENV_SMOKE" not in makefile
    assert ".venv-lint" not in makefile
    assert ".github/scripts/release_notes.py" not in makefile
    assert ".github/scripts docs/site -type f" in makefile
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".venv-smoke" not in gitignore and ".venv-lint" not in gitignore


def test_repository_automation_configuration_is_project_local() -> None:
    dependabot = (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
    assert dependabot.count("package-ecosystem:") == 2
    assert dependabot.count("directory: /") == 2
    assert "package-ecosystem: pip" in dependabot
    assert "package-ecosystem: github-actions" in dependabot
    exceptions = (ROOT / ".github/dependency-audit-exceptions.json").read_text(
        encoding="utf-8"
    )
    assert exceptions == '{\n  "exceptions": []\n}\n'


def test_reference_provenance_and_contract_namespaces_are_permanent() -> None:
    development = (ROOT / "docs/maintenance/development.md").read_text(encoding="utf-8")
    assert "53ce1d0584ecd015edaf5583aeed216ed7b28ca0" in development
    for prefix in ("PKG", "DEP", "CIR", "SEC", "API", "CMP"):
        assert f"`{prefix}`" in development
    assert "../joplin-md-sync" not in development


def test_dependency_policy_runs_without_an_external_checkout() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/dependency_policy.py"), "validate"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
