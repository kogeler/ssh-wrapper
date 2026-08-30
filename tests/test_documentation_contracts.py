# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Traceability and separation checks for maintained documentation."""

from __future__ import annotations

import ast
import re
import runpy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import ssh_wrapper

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CONTRACTS = DOCS / "contracts"
CONTRACT_FILES = {
    "api.md",
    "ci_releases.md",
    "compatibility.md",
    "dependencies.md",
    "package.md",
    "README.md",
    "security.md",
}
CONTRACT_PREFIXES = {
    "api.md": "API",
    "ci_releases.md": "CIR",
    "compatibility.md": "CMP",
    "dependencies.md": "DEP",
    "package.md": "PKG",
    "security.md": "SEC",
}
USER_FILES = {"api.md", "installation.md", "security.md", "usage.md"}
MAINTENANCE_FILES = {
    "architecture.md",
    "dependencies.md",
    "development.md",
    "releases.md",
    "security.md",
}
ASSERTION = re.compile(r"^### `([A-Z]{3}-[0-9]{3})` - .+$", re.MULTILINE)
EVIDENCE = re.compile(r"^- \[`[^`]+`\]\(([^)]+)\) - `([^`]+)`$", re.MULTILINE)
MARKDOWN_LINK = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
NORMATIVE_WORDS = re.compile(r"\b(?:MUST|MUST NOT|SHOULD|SHOULD NOT|MAY)\b")


def _node_exists(path: Path, node_id: str) -> bool:
    parts = node_id.split("::")
    if Path(parts[0]) != path.relative_to(ROOT) or len(parts) < 2:
        return False
    body: list[ast.stmt] = ast.parse(
        path.read_text(encoding="utf-8"), filename=str(path)
    ).body
    for name in parts[1:]:
        match = next(
            (
                node
                for node in body
                if isinstance(
                    node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                )
                and node.name == name
            ),
            None,
        )
        if match is None:
            return False
        body = match.body if isinstance(match, ast.ClassDef) else []
    return True


def _heading_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            continue
        heading = line.lstrip("#").strip().replace("`", "")
        slug = re.sub(r"[^\w\s-]", "", heading.lower())
        anchors.add(re.sub(r"[-\s]+", "-", slug).strip("-"))
    return anchors


def test_contract_assertions_have_unique_ids_and_real_evidence() -> None:
    seen: set[str] = set()
    for path in sorted(CONTRACTS.glob("*.md")):
        if path.name == "README.md":
            continue
        content = path.read_text(encoding="utf-8")
        matches = list(ASSERTION.finditer(content))
        assert matches, path
        prefix = CONTRACT_PREFIXES[path.name]
        assert [match.group(1) for match in matches] == [
            f"{prefix}-{number:03d}" for number in range(1, len(matches) + 1)
        ]
        for index, match in enumerate(matches):
            assertion_id = match.group(1)
            assert assertion_id not in seen, assertion_id
            seen.add(assertion_id)
            end = (
                matches[index + 1].start() if index + 1 < len(matches) else len(content)
            )
            section = content[match.end() : end]
            assert "\n**Contract:** " in section, assertion_id
            assert "\n**Evidence:**\n" in section, assertion_id
            evidence = EVIDENCE.findall(section)
            assert evidence, assertion_id
            for relative_link, node_id in evidence:
                target = (path.parent / relative_link).resolve()
                assert target.is_file(), (assertion_id, relative_link)
                assert target == (ROOT / node_id.split("::", 1)[0]).resolve(), (
                    assertion_id,
                    relative_link,
                    node_id,
                )
                assert _node_exists(target, node_id), (assertion_id, node_id)


def test_documentation_tree_navigation_and_language_are_separated() -> None:
    assert {path.name for path in CONTRACTS.glob("*.md")} == CONTRACT_FILES
    assert {path.name for path in (DOCS / "user").glob("*.md")} == USER_FILES
    assert {path.name for path in (DOCS / "maintenance").glob("*.md")} == (
        MAINTENANCE_FILES
    )
    assert {path.name for path in DOCS.glob("*.md")} == {"index.md"}
    assert not any(path.is_file() for path in (ROOT / "doc").rglob("*"))

    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "site_url: https://kogeler.github.io/ssh-wrapper/" in mkdocs
    assert "site_author: kogeler" in mkdocs
    for directory, names in (
        ("contracts", CONTRACT_FILES),
        ("user", USER_FILES),
        ("maintenance", MAINTENANCE_FILES),
    ):
        for name in names:
            assert f"{directory}/{name}" in mkdocs
    excluded = mkdocs.split("exclude_docs:", 1)[1].split("markdown_extensions:", 1)[0]
    for name in ("hooks.py", "llms.txt", "robots.txt", "__pycache__"):
        assert name in excluded

    non_contracts = [
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        DOCS / "index.md",
        *sorted((DOCS / "user").glob("*.md")),
    ]
    non_contracts.extend(sorted((DOCS / "maintenance").glob("*.md")))
    for path in non_contracts:
        assert NORMATIVE_WORDS.search(path.read_text(encoding="utf-8")) is None, path

    assert (DOCS / "site/robots.txt").read_text(encoding="utf-8") == (
        "User-agent: *\nAllow: /\n\n"
        "Sitemap: https://kogeler.github.io/ssh-wrapper/sitemap.xml\n"
    )
    assert (
        (DOCS / "site/llms.txt")
        .read_text(encoding="utf-8")
        .startswith("# ssh-wrapper\n")
    )


def test_all_source_documentation_links_and_anchors_resolve() -> None:
    for path in DOCS.rglob("*.md"):
        for raw_target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
            target = raw_target.split(maxsplit=1)[0]
            if target.startswith(("http://", "https://", "mailto:")):
                assert not target.startswith("http://"), (path, target)
                continue
            if target.startswith("#"):
                assert target[1:] in _heading_anchors(path), (path, target)
                continue
            assert not target.startswith("/"), (path, target)
            relative, _, fragment = target.partition("#")
            resolved = (path.parent / relative).resolve()
            assert resolved.is_relative_to(ROOT), (path, target)
            assert resolved.is_file(), (path, target)
            if fragment and resolved.suffix == ".md":
                assert fragment in _heading_anchors(resolved), (path, target)


def test_site_hook_rewrites_only_repository_external_links_and_copies_root_files(
    tmp_path: Path,
) -> None:
    hooks = runpy.run_path(DOCS / "site/hooks.py")
    rewrite = cast("Any", hooks["on_page_markdown"])
    publish = cast("Any", hooks["on_post_build"])
    page = SimpleNamespace(file=SimpleNamespace(abs_src_path=CONTRACTS / "api.md"))
    config = {"docs_dir": str(DOCS), "site_dir": str(tmp_path)}

    rendered = rewrite(
        "[test](../../tests/test_public_api.py) [user](../user/api.md)",
        page=page,
        config=config,
    )
    assert (
        "[test](https://github.com/kogeler/ssh-wrapper/blob/main/"
        "tests/test_public_api.py)" in rendered
    )
    assert "[user](../user/api.md)" in rendered

    publish(config=config)
    for name in ("llms.txt", "robots.txt"):
        assert (tmp_path / name).read_bytes() == (DOCS / "site" / name).read_bytes()


def test_public_python_examples_compile_and_import_only_root_api() -> None:
    documents = [ROOT / "README.md", *sorted((DOCS / "user").glob("*.md"))]
    snippets = 0
    for path in documents:
        content = path.read_text(encoding="utf-8")
        for match in re.finditer(r"```python\n(.*?)```", content, re.DOTALL):
            snippets += 1
            source = match.group(1)
            tree = compile(
                source,
                f"{path}:example-{snippets}",
                "exec",
                flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
                dont_inherit=True,
            )
            assert tree is not None
            syntax = ast.parse(source)
            for node in ast.walk(syntax):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.startswith("ssh_wrapper")
                ):
                    assert node.module == "ssh_wrapper", (path, node.module)
                    assert all(
                        alias.name in ssh_wrapper.__all__ for alias in node.names
                    ), (
                        path,
                        [alias.name for alias in node.names],
                    )
    assert snippets == 4


def test_public_support_statements_match_package_metadata() -> None:
    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    index = (DOCS / "index.md").read_text(encoding="utf-8")
    installation = (DOCS / "user/installation.md").read_text(encoding="utf-8")
    llms = (DOCS / "site/llms.txt").read_text(encoding="utf-8")

    assert 'requires-python = ">=3.13,<3.15"' in metadata
    assert '"Programming Language :: Python :: Implementation :: CPython"' in metadata
    assert '"Operating System :: POSIX :: Linux"' in metadata
    assert "- CPython 3.13 or 3.14\n- Linux\n" in readme
    assert "- Linux as the supported runtime platform" in index
    assert "Use CPython 3.13 or 3.14 on Linux" in installation
    assert "CPython 3.13 and 3.14 library for Linux" in " ".join(llms.split())
