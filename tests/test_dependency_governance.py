# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Evidence for exact dependency audiences, snapshots, and audit exceptions."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tools import dependency_audit, dependency_policy

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "tools/dependency_policy.py"
SNAPSHOT = ROOT / ".github/scripts/dependency_snapshot.py"
AUDIT = ROOT / "tools/dependency_audit.py"
LOCKS = (
    "requirements-dev.txt",
    "requirements-test.txt",
    "requirements-package.txt",
    "requirements-docs.txt",
)
EXACT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9._,-]+\])?==[^\s;]+$")


def run(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *(str(argument) for argument in arguments)],
        check=False,
        capture_output=True,
        text=True,
    )


def copy_inputs(destination: Path) -> None:
    shutil.copy2(ROOT / "pyproject.toml", destination / "pyproject.toml")
    for name in LOCKS:
        shutil.copy2(ROOT / name, destination / name)
        input_path = Path(name).with_suffix(".in")
        shutil.copy2(ROOT / input_path, destination / input_path)


def test_direct_dependencies_are_exact_and_scoped() -> None:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = document["project"]

    assert project["dependencies"] == []
    assert "optional-dependencies" not in project
    groups = {
        audience: [
            line
            for line in (ROOT / lock)
            .with_suffix(".in")
            .read_text(encoding="utf-8")
            .splitlines()
            if line and not line.startswith("#")
        ]
        for audience, lock in dependency_policy.LOCK_DEFINITIONS
    }
    assert set(groups) == {"dev", "test", "package", "docs"}
    assert all(
        group and all(EXACT.fullmatch(item) for item in group)
        for group in groups.values()
    )
    memberships: dict[str, set[str]] = {}
    for group, requirements in groups.items():
        for requirement in requirements:
            name, _, _version = requirement.partition("==")
            normalized = name.partition("[")[0].replace("_", "-").lower()
            memberships.setdefault(normalized, set()).add(group)
    overlaps = {
        name: audiences for name, audiences in memberships.items() if len(audiences) > 1
    }
    assert overlaps == {}
    assert {requirement.partition("==")[0] for requirement in groups["package"]} == {
        "build",
        "setuptools",
        "wheel",
    }
    assert any(item.startswith("mypy==") for item in groups["dev"])
    assert all("mypy" not in item for item in groups["package"])
    assert all("pip-licenses" not in item for item in groups["dev"])
    assert not (ROOT / "requirements-lint.txt").exists()
    assert not (ROOT / "tools/lint/pyproject.toml").exists()

    bootstrap = document["dependency-groups"]["resolver-bootstrap"]
    assert bootstrap and all(EXACT.fullmatch(item) for item in bootstrap)
    assert document["build-system"]["requires"] == ["setuptools>=84"]
    completed = run(POLICY, "bootstrap")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        requirement.partition("[")[0] if "[" in requirement else requirement
        for requirement in bootstrap
    ]
    assert dependency_policy.validate_resolver_bootstrap(ROOT) == {
        requirement.partition("==")[0]: requirement.partition("==")[2]
        for requirement in bootstrap
    }
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "LOCK_BOOTSTRAP" not in makefile
    assert "tools/dependency_policy.py bootstrap" in makefile
    bootstrap_recipe = makefile.split("$(DEPS_LOCK_STAMP):", 1)[1].split(
        "venv-lock:", 1
    )[0]
    assert "--no-deps --only-binary=:all:" in bootstrap_recipe
    assert "--extra=" not in makefile
    freeze_recipe = makefile.split("freeze-check:", 1)[1].split(
        "lock-platform-check:", 1
    )[0]
    assert 'cp -- $(LOCKS) "$$temporary/"' in freeze_recipe
    lock_recipe = makefile.split("\nlock:", 1)[1].split("\nrefresh-dependencies:", 1)[0]
    assert lock_recipe.rstrip().endswith("@$(MAKE) dependency-validate")


@pytest.mark.parametrize("lock_state", ("stale", "missing"))
def test_resolver_bootstrap_is_available_before_lock_regeneration(
    tmp_path: Path, lock_state: str
) -> None:
    copy_inputs(tmp_path)
    project = tmp_path / "pyproject.toml"
    bootstrap = dependency_policy.resolver_bootstrap(tmp_path)
    project.write_text(
        project.read_text(encoding="utf-8").replace(
            f'"build=={bootstrap["build"]}"', '"build==0.0.1"'
        ),
        encoding="utf-8",
    )
    bootstrap["build"] = "0.0.1"
    if lock_state == "missing":
        for name in LOCKS:
            (tmp_path / name).unlink()

    completed = run(POLICY, "--root", tmp_path, "bootstrap")
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        f"{name}=={version}" for name, version in bootstrap.items()
    ]

    rejected = run(POLICY, "--root", tmp_path, "validate")
    assert rejected.returncode == 1
    assert (
        "resolver bootstrap versions differ from audience locks"
        if lock_state == "stale"
        else "cannot read"
    ) in rejected.stderr


@pytest.mark.parametrize(
    "requirement", ("build>=1", "build==1.*", "unexpected==1", "pip==1")
)
def test_resolver_bootstrap_rejects_invalid_source_without_locks(
    tmp_path: Path, requirement: str
) -> None:
    project = tmp_path / "pyproject.toml"
    bootstrap = dependency_policy.resolver_bootstrap(ROOT)
    project.write_text(
        (ROOT / "pyproject.toml")
        .read_text(encoding="utf-8")
        .replace(f'"build=={bootstrap["build"]}"', f'"{requirement}"'),
        encoding="utf-8",
    )
    completed = run(POLICY, "--root", tmp_path, "bootstrap")
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert "dependency policy error" in completed.stderr


@pytest.mark.parametrize(
    "content",
    (
        "",
        "ruff>=1",
        "ruff==1.*",
        "-r requirements.in",
        "ruff==1; python_version >= '3'",
        "ruff==1\nRuff==1",
    ),
)
def test_native_inputs_reject_nonexact_or_ambiguous_requirements(
    tmp_path: Path, content: str
) -> None:
    copy_inputs(tmp_path)
    (tmp_path / "requirements-dev.in").write_text(content, encoding="utf-8")
    completed = run(POLICY, "--root", tmp_path, "validate")
    assert completed.returncode == 1


def test_native_inputs_reject_duplicate_owners_and_extra_audiences(
    tmp_path: Path,
) -> None:
    copy_inputs(tmp_path)
    development = tmp_path / "requirements-dev.in"
    development.write_text("pytest==9.1.1\n", encoding="utf-8")
    completed = run(POLICY, "--root", tmp_path, "validate")
    assert completed.returncode == 1 and "must be disjoint" in completed.stderr
    shutil.copy2(ROOT / "requirements-dev.in", development)
    (tmp_path / "requirements.in").write_text("example==1\n", encoding="utf-8")
    completed = run(POLICY, "--root", tmp_path, "validate")
    assert completed.returncode == 1 and "exactly four" in completed.stderr


def test_all_committed_locks_are_nonempty_pip_compile_hash_locks() -> None:
    assert {path.name for path in ROOT.glob("requirements*.txt")} == set(LOCKS)
    for name in LOCKS:
        content = (ROOT / name).read_text(encoding="utf-8")
        assert "autogenerated by pip-compile with Python 3.14" in content
        pins = [
            line
            for line in content.splitlines()
            if line and not line[0].isspace() and not line.startswith("#")
        ]
        assert pins
        assert all(line.endswith(" \\") for line in pins)
        assert content.count("--hash=sha256:") >= len(pins)


def test_snapshot_is_deterministic_and_contains_every_audience(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    for output in (first, second):
        completed = run(SNAPSHOT, "--output", output)
        assert completed.returncode == 0, completed.stderr
    assert first.read_bytes() == second.read_bytes()
    manifests = json.loads(first.read_text(encoding="utf-8"))["manifests"]
    assert set(manifests) == set(LOCKS)
    assert (
        manifests["requirements-dev.txt"]["resolved"]["ruff"]["relationship"]
        == "direct"
    )
    assert (
        manifests["requirements-test.txt"]["resolved"]["pytest"]["relationship"]
        == "direct"
    )
    assert (
        manifests["requirements-package.txt"]["resolved"]["build"]["relationship"]
        == "direct"
    )
    assert (
        manifests["requirements-docs.txt"]["resolved"]["mkdocs-material"][
            "relationship"
        ]
        == "direct"
    )
    for manifest in manifests.values():
        assert manifest["resolved"]
        assert {item["scope"] for item in manifest["resolved"].values()} == {
            "development"
        }


def test_snapshot_rejects_hashless_and_version_drifted_inputs(tmp_path: Path) -> None:
    copy_inputs(tmp_path)
    lock = tmp_path / "requirements-dev.txt"
    content = lock.read_text(encoding="utf-8")
    lock.write_text(
        re.sub(
            r"(ruff==[^\n]+\\\n)(?:[ \t]+--hash=sha256:[0-9a-f]{64}(?: \\)?\n)+",
            r"\1",
            content,
            count=1,
        ),
        encoding="utf-8",
    )
    hashless = run(SNAPSHOT, "--root", tmp_path, "--output", tmp_path / "snapshot.json")
    assert hashless.returncode == 1
    assert "has no SHA-256 hash" in hashless.stderr

    shutil.copy2(ROOT / "requirements-dev.txt", lock)
    source = tmp_path / "requirements-dev.in"
    source.write_text(
        re.sub(r"ruff==[^\n]+", "ruff==0.0.1", source.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    drift = run(SNAPSHOT, "--root", tmp_path, "--output", tmp_path / "snapshot.json")
    assert drift.returncode == 1
    assert "direct versions differ" in drift.stderr


def test_regenerated_lock_comparison_ignores_only_the_header(tmp_path: Path) -> None:
    for name in LOCKS:
        shutil.copy2(ROOT / name, tmp_path / name)
    development = tmp_path / "requirements-dev.txt"
    development.write_text(
        re.sub(
            r"autogenerated by pip-compile with Python [^\n]+",
            "autogenerated by pip-compile with Python 9.99",
            development.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )
    accepted = run(POLICY, "compare", "--candidate-root", tmp_path)
    assert accepted.returncode == 0, accepted.stderr

    development.write_text(
        re.sub(
            r"sha256:[0-9a-f]{64}",
            "sha256:" + "0" * 64,
            development.read_text(encoding="utf-8"),
            count=1,
        ),
        encoding="utf-8",
    )
    rejected = run(POLICY, "compare", "--candidate-root", tmp_path)
    assert rejected.returncode == 1
    assert "regenerated pins or hashes differ" in rejected.stderr


def audit_files(
    tmp_path: Path, report: object, exceptions: object
) -> tuple[Path, Path]:
    report_path = tmp_path / "report.json"
    exception_path = tmp_path / "exceptions.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    exception_path.write_text(json.dumps(exceptions), encoding="utf-8")
    return report_path, exception_path


def test_audit_accepts_only_the_exact_reviewed_set(tmp_path: Path) -> None:
    report = {
        "dependencies": [
            {"name": "Example_Pkg", "version": "1.2", "vulns": [{"id": "ADV-1"}]}
        ]
    }
    accepted = {
        "exceptions": [
            {
                "package": "example-pkg",
                "version": "1.2",
                "vulnerabilities": ["ADV-1"],
                "reason": "Reviewed",
            }
        ]
    }
    report_path, exception_path = audit_files(tmp_path, report, accepted)
    completed = run(AUDIT, "--report", report_path, "--exceptions", exception_path)
    assert completed.returncode == 0, completed.stderr

    exception_path.write_text('{"exceptions": []}', encoding="utf-8")
    unexpected = run(AUDIT, "--report", report_path, "--exceptions", exception_path)
    assert unexpected.returncode == 1
    assert "unexpected vulnerabilities" in unexpected.stderr

    clean_path, stale_path = audit_files(tmp_path, {"dependencies": []}, accepted)
    stale = run(AUDIT, "--report", clean_path, "--exceptions", stale_path)
    assert stale.returncode == 1
    assert "stale vulnerability exceptions" in stale.stderr


def test_live_audit_includes_locks_and_exact_resolver_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []
    bootstrap_lines: list[str] = []
    expected_bootstrap = run(POLICY, "bootstrap").stdout.splitlines()

    def completed(
        command: list[str], **_options: object
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "--no-deps" in command:
            requirement = Path(command[command.index("--requirement") + 1])
            bootstrap_lines.extend(requirement.read_text(encoding="utf-8").splitlines())
        return subprocess.CompletedProcess(
            command, 0, stdout='{"dependencies": []}', stderr=""
        )

    monkeypatch.setattr(dependency_audit.subprocess, "run", completed)

    assert dependency_audit.live_findings() == frozenset()
    assert len(commands) == len(LOCKS) + 1
    assert sum("--require-hashes" in command for command in commands) == len(LOCKS)
    assert sum("--no-deps" in command for command in commands) == 1
    assert bootstrap_lines == expected_bootstrap

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "tools/dependency_policy.py bootstrap" in makefile
    assert "audit-raw: venv-dev dependency-validate" in makefile
    assert "--disable-pip --no-deps" in makefile
