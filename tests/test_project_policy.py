# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Tests for the independent local governance surface."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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
        "acceptance-image",
        "test-acceptance-support",
        "test-acceptance",
        "test-fido",
        "venv-path",
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
    assert "exclude-paths:\n      - pyproject.toml" in dependabot
    exceptions = (ROOT / ".github/dependency-audit-exceptions.json").read_text(
        encoding="utf-8"
    )
    assert exceptions == '{\n  "exceptions": []\n}\n'


@pytest.mark.parametrize("engine_status", (0, 23))
def test_container_validation_uses_host_buses_and_propagates_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine_status: int
) -> None:
    shutil.copy2(ROOT / "Makefile", tmp_path / "Makefile")
    (tmp_path / "tools").mkdir()
    shutil.copy2(ROOT / "tools/machine.py", tmp_path / "tools/machine.py")
    commands = tmp_path / "bin"
    commands.mkdir()
    engine = commands / "podman"
    engine.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "print(json.dumps({'argv': sys.argv[1:], 'environment': {\n"
        "    name: os.environ.get(name) for name in (\n"
        "        'DBUS_SESSION_BUS_ADDRESS', 'DBUS_SYSTEM_BUS_ADDRESS',\n"
        "        'XDG_RUNTIME_DIR')}}))\n"
        f"sys.exit({engine_status})\n",
        encoding="utf-8",
    )
    engine.chmod(0o755)
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/private/session-bus")
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", "unix:path=/private/system-bus")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    environment = dict(os.environ)
    for name in ("CONTAINER", "MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES"):
        environment.pop(name, None)
    environment.update(
        {"PATH": f"{commands}:{os.environ['PATH']}", "PY": sys.executable}
    )
    completed = subprocess.run(
        ["make", "--no-print-directory", "validate-actions"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (completed.returncode == 0) == (engine_status == 0), completed.stderr
    invocation = json.loads(completed.stdout)
    assert invocation["environment"] == {
        "DBUS_SESSION_BUS_ADDRESS": None,
        "DBUS_SYSTEM_BUS_ADDRESS": None,
        "XDG_RUNTIME_DIR": str(tmp_path / "runtime"),
    }
    assert os.environ["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/private/session-bus"
    assert os.environ["DBUS_SYSTEM_BUS_ADDRESS"] == "unix:path=/private/system-bus"
    arguments = invocation["argv"]
    assert arguments[:5] == [
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--cap-drop=all",
    ]
    assert "--security-opt=no-new-privileges" in arguments
    assert arguments[arguments.index("--volume") + 1] == f"{tmp_path}:/repo:ro,z"
    assert arguments[arguments.index("--workdir") + 1] == "/repo"
    assert any(
        re.fullmatch(r"docker.io/rhysd/actionlint@sha256:[0-9a-f]{64}", argument)
        for argument in arguments
    )
    assert arguments[-2:] == ["-config-file", ".github/actionlint.yaml"]
    assert not any(
        argument.startswith(("--cgroup", "--events-backend")) for argument in arguments
    )


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


def test_fido_gate_is_explicit_and_excluded_from_automatic_validation() -> None:
    makefile = (ROOT / "Makefile").read_text()
    fido = re.search(r"^test-fido:.*?(?=\n\S)", makefile, re.MULTILINE | re.DOTALL)
    assert fido is not None and "-m fido tests_acceptance" in fido.group()
    for target in ("ci", "check", "test-acceptance"):
        recipe = re.search(
            rf"^{target}:.*?(?=\n\S)", makefile, re.MULTILINE | re.DOTALL
        )
        assert recipe is not None and "fido" not in recipe.group()
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        assert "test-fido" not in workflow.read_text()
    source = (ROOT / "tests_acceptance/test_fido.py").read_text()
    assert "pytest.mark.fido" in source and "pytest.mark.acceptance" not in source
    assert 'os.environ.get("FIDO_IDENTITY")' in source
    assert "_exercise_openssh(tmp_path, monkeypatch, fido_identity=identity)" in source


def test_venv_path_is_exposed_through_make() -> None:
    result = subprocess.run(
        ["make", "--no-print-directory", "venv-path"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert re.fullmatch(r"\.venvs/[0-9a-f]{64}/cpython-3\.(13|14)\n", result.stdout)
