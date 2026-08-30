# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Regression tests for the independent repository boundary."""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import ssh_wrapper

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ssh_wrapper"


def test_version_metadata_is_synchronized() -> None:
    version = (ROOT / ".version").read_text(encoding="utf-8").strip()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version)
    assert project["project"]["name"] == "ssh-wrapper"
    assert project["project"]["dynamic"] == ["version"]
    assert "version" not in project["project"]
    assert project["tool"]["setuptools"]["dynamic"]["version"] == {"file": ".version"}
    assert project["project"]["dependencies"] == []
    assert ssh_wrapper.__version__ == version
    assert f"## [{version}] - " in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_python_and_copyright_ownership_are_exact() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]

    assert project["requires-python"] == ">=3.13,<3.15"
    assert {
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    }.issubset(project["classifiers"])
    assert (
        "Programming Language :: Python :: Implementation :: CPython"
        in project["classifiers"]
    )
    assert "Operating System :: POSIX :: Linux" in project["classifiers"]
    assert project["authors"] == [{"name": "kogeler"}]
    assert project["maintainers"] == [{"name": "kogeler"}]
    assert "Copyright (c) 2026 kogeler" in (ROOT / "LICENSE").read_text(
        encoding="utf-8"
    )
    assert "contributors" not in (ROOT / "LICENSE").read_text(encoding="utf-8")

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert 'sys.implementation.name != "cpython"' in makefile
    assert "SUPPORTED_PYTHONS := 3.13 3.14" in makefile
    assert "sys.version_info[:2] not in {(3, 13), (3, 14)}" in makefile


def test_runtime_sources_parse_with_minimum_supported_grammar() -> None:
    for path in PACKAGE.glob("*.py"):
        ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
            feature_version=(3, 13),
        )


def test_runtime_imports_only_standard_library_or_local_modules() -> None:
    for path in PACKAGE.glob("*.py"):
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    alias.name.partition(".")[0] in sys.stdlib_module_names
                    for alias in node.names
                ), path
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module is not None
                assert node.module.partition(".")[0] in sys.stdlib_module_names, path


def test_local_documentation_links_are_relative_and_resolve() -> None:
    link_pattern = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
    documents = [
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        *sorted((ROOT / "docs").rglob("*.md")),
    ]

    for document in documents:
        content = document.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(content):
            target = raw_target.split("#", 1)[0]
            if not target:
                continue
            if target.startswith("https://"):
                assert target.startswith(("https://github.com/kogeler/ssh-wrapper",)), (
                    document,
                    raw_target,
                )
                continue
            assert "://" not in target and not target.startswith("/"), (
                document,
                raw_target,
            )
            assert (document.parent / target).resolve().is_relative_to(ROOT.resolve())
            assert (document.parent / target).exists(), (document, raw_target)


def test_pypi_readme_links_are_portable_https_targets() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"(?<!!)\[[^]]+\]\(([^)]+)\)", readme)

    assert links
    assert all(target.startswith("https://") for target in links)
