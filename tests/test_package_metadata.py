# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Static evidence for public PyPI metadata and source-distribution policy."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pypi_metadata_exposes_exact_public_routes_and_python() -> None:
    document = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = document["project"]

    assert project["name"] == "ssh-wrapper"
    assert project["dynamic"] == ["version"]
    assert project["description"] == (
        "One-auth OpenSSH ControlMaster lifecycle with mux-only channels"
    )
    assert project["readme"] == {
        "file": "README.md",
        "content-type": "text/markdown",
    }
    assert project["requires-python"] == ">=3.13,<3.15"
    assert project["authors"] == project["maintainers"] == [{"name": "kogeler"}]
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert project["keywords"] == [
        "openssh",
        "ssh",
        "controlmaster",
        "multiplexing",
        "asyncio",
    ]
    assert project["classifiers"] == [
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Networking",
        "Typing :: Typed",
    ]
    assert project["dependencies"] == []
    assert not {"scripts", "gui-scripts", "entry-points"}.intersection(project)
    assert project["urls"] == {
        "Homepage": "https://kogeler.github.io/ssh-wrapper/",
        "Documentation": "https://kogeler.github.io/ssh-wrapper/",
        "Repository": "https://github.com/kogeler/ssh-wrapper",
        "Issues": "https://github.com/kogeler/ssh-wrapper/issues",
        "Changelog": "https://github.com/kogeler/ssh-wrapper/blob/main/CHANGELOG.md",
    }
    assert document["build-system"]["build-backend"] == "setuptools.build_meta"
    assert document["build-system"]["requires"] == [
        requirement
        for requirement in project["optional-dependencies"]["package"]
        if requirement.startswith("setuptools==")
    ]


def test_pypi_readme_uses_only_portable_https_links() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\[[^]]*\]\(([^)]+)\)", readme)

    assert links
    assert all(link.startswith("https://") for link in links)
    assert "../" not in readme
    assert "/home/" not in readme

    prefix = "https://kogeler.github.io/ssh-wrapper/"
    pages_routes = [
        link.removeprefix(prefix) for link in links if link.startswith(prefix)
    ]
    assert pages_routes
    for route in pages_routes:
        assert route == route.lower()
        if not route:
            source = ROOT / "docs/index.md"
        else:
            candidate = ROOT / "docs" / route.rstrip("/")
            source = (
                candidate / "README.md"
                if candidate.is_dir()
                else candidate.with_suffix(".md")
            )
        assert source.is_file(), (route, source)


def test_public_install_examples_use_the_current_exact_version() -> None:
    version = (ROOT / ".version").read_text(encoding="utf-8").strip()
    documents = (
        ROOT / "README.md",
        ROOT / "docs/user/installation.md",
    )

    found: list[str] = []
    for path in documents:
        content = path.read_text(encoding="utf-8")
        assert "python3.13" in content
        assert "python3.14" in content
        found.extend(re.findall(r'ssh-wrapper==([^"\s]+)', content))
    assert found and set(found) == {version}


def test_sdist_manifest_excludes_nonproduct_trees() -> None:
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    for directory in (
        ".github",
        "doc",
        "docs",
        "tests",
        "tests_acceptance",
        "tmp",
        "tools",
    ):
        assert f"prune {directory}\n" in manifest
    assert "recursive-include ssh_wrapper *.py py.typed" in manifest


def test_inline_typing_configuration_is_packaged() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["tool"]["setuptools"]["package-data"] == {
        "ssh_wrapper": ["py.typed"]
    }
    assert (ROOT / "ssh_wrapper/py.typed").read_bytes() in {b"", b"\n"}
    verifier = (ROOT / "tools/verify_distribution.py").read_text(encoding="utf-8")
    assert '"ssh_wrapper/py.typed"' in verifier
    assert 'message.get("Keywords")' in verifier
    assert 'message.get_all("Classifier", [])' in verifier
    assert 'message.get_all("Requires-Dist", [])' in verifier
    assert 'files["PKG-INFO"] != files["ssh_wrapper.egg-info/PKG-INFO"]' in verifier
    assert "mypy" in (ROOT / "tools/smoke_distribution.py").read_text(encoding="utf-8")


def test_package_make_contract_builds_smokes_and_reuses_exact_pair() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "package: build confinement-test checksums" in makefile
    assert "smoke: package smoke-wheel smoke-sdist" in makefile
    assert "reproducibility: venv-package" in makefile
    assert ci.count("make package smoke reproducibility") == 1
    assert ci.count("actions/upload-artifact@") == 1
    assert release.count("make build smoke-wheel smoke-sdist") == 0
    assert release.count("actions/download-artifact@") == 2
    assert "deleteReleaseAsset" not in release
