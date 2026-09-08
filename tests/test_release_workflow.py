# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Execute the actual release workflow scripts against offline API fixtures."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
HEAD = "2" * 40
TAGGED = "1" * 40
VERSION = "1.2.3"
REPOSITORY = "kogeler/ssh-wrapper"
NODE = shutil.which("node")

MOCK_GITHUB = r"""
const fs = require("node:fs");
const { script, state } = JSON.parse(fs.readFileSync(0, "utf8"));
const outputs = {};
const reads = [];
const absent = () => { throw Object.assign(new Error("Not found"), { status: 404 }); };
const repos = {
  getContent: async ({ path, ref }) => {
    reads.push([ref, path]);
    const content = state.sources[ref]?.[path];
    if (typeof content !== "string") throw new Error("Unexpected source read");
    return { data: { type: "file", encoding: "base64",
      content: Buffer.from(content).toString("base64") } };
  },
  listReleases: async () => state.release ? [state.release] : [],
  listReleaseAssets: async () => state.assets,
  getReleaseByTag: async () => state.release ? { data: state.release } : absent(),
  getLatestRelease: async () => state.latest ? { data: { tag_name: state.latest } } : absent(),
};
const github = {
  rest: { repos, git: {
    getRef: async () => state.tag ? { data: { object: { type: "commit", sha: state.tag } } } : absent(),
    getTag: async () => { throw new Error("Unexpected annotated tag read"); },
  } },
  paginate: async (method, args) => method(args),
  request: async (route, { asset_id }) => {
    if (route !== "GET /repos/{owner}/{repo}/releases/assets/{asset_id}") {
      throw new Error("Unexpected API call: " + route);
    }
    return { data: Buffer.from(state.assetBytes[asset_id]) };
  },
};
const core = { setOutput: (name, value) => { outputs[name] = value; }, notice: () => {} };
const context = { repo: { owner: "kogeler", repo: "ssh-wrapper" },
  sha: "2".repeat(40), ref: "refs/heads/main", eventName: "push" };
const fetch = async (url) => {
  if (url !== "https://pypi.org/pypi/ssh-wrapper/1.2.3/json") throw new Error("Unexpected URL");
  return { status: state.pypi ? 200 : 404, ok: Boolean(state.pypi), json: async () => state.pypi };
};
const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;
(async () => {
  let error = null;
  try {
    await new AsyncFunction("github", "core", "context", "fetch", script)(github, core, context, fetch);
  } catch (caught) { error = caught.message; }
  process.stdout.write(JSON.stringify({ outputs, reads, error }));
})();
"""


def _block(workflow: str, step: str, field: str) -> str:
    content = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
    remainder = content.split(f"- name: {step}\n", 1)[1].split(f"{field}: |\n", 1)[1]
    lines = remainder.splitlines(keepends=True)
    indent = len(lines[0]) - len(lines[0].lstrip())
    selected = []
    for line in lines:
        if line.strip() and not line.startswith(" " * indent):
            break
        selected.append(line)
    return textwrap.dedent("".join(selected))


def _notes(entry: str) -> str:
    return f"- {entry}\n\nFull changelog: https://github.com/{REPOSITORY}/blob/v{VERSION}/CHANGELOG.md\n"


def _state() -> dict[str, Any]:
    files = {
        f"ssh_wrapper-{VERSION}-py3-none-any.whl": "wheel bytes",
        f"ssh_wrapper-{VERSION}.tar.gz": "sdist bytes",
    }
    urls = [
        {
            "filename": name,
            "packagetype": "sdist" if name.endswith(".gz") else "bdist_wheel",
            "size": len(data),
            "digests": {"sha256": hashlib.sha256(data.encode()).hexdigest()},
            "yanked": False,
        }
        for name, data in files.items()
    ]
    files["SHA256SUMS.txt"] = "".join(
        f"{hashlib.sha256(data.encode()).hexdigest()}  {name}\n"
        for name, data in sorted(files.items())
    )
    return {
        "sources": {
            HEAD: {
                ".version": VERSION,
                "CHANGELOG.md": f"## Unreleased\n\n- Pending.\n\n## [{VERSION}] - 2026-08-30\n\n- Head entry.\n",
            },
            TAGGED: {
                ".version": VERSION,
                "CHANGELOG.md": f"## [{VERSION}] - 2026-08-30\n\n- Original entry.\n",
            },
        },
        "tag": TAGGED,
        "release": {
            "id": 1,
            "tag_name": f"v{VERSION}",
            "name": f"v{VERSION}",
            "body": _notes("Original entry."),
            "target_commitish": TAGGED,
            "draft": False,
            "prerelease": False,
        },
        "assets": [
            {"id": index, "name": name, "size": len(data), "state": "uploaded"}
            for index, (name, data) in enumerate(files.items())
        ],
        "assetBytes": {index: data for index, data in enumerate(files.values())},
        "pypi": {"info": {"name": "ssh-wrapper", "version": VERSION}, "urls": urls},
        "latest": "v1.2.2",
    }


def _execute(script: str, state: dict[str, Any], **environment: str) -> dict[str, Any]:
    if NODE is None:
        pytest.skip("Node.js is needed to execute GitHub Actions JavaScript fixtures")
    completed = subprocess.run(
        [NODE, "-e", MOCK_GITHUB],
        input=json.dumps({"script": script, "state": state}),
        env={
            **os.environ,
            "EXPECTED_REPOSITORY": REPOSITORY,
            "PYPI_PROJECT": "ssh-wrapper",
            **environment,
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _inspect(state: dict[str, Any]) -> dict[str, Any]:
    return _execute(
        _block(
            "release.yml", "Inspect both publication targets independently", "script"
        ),
        state,
    )


def test_published_release_uses_tagged_source_and_needs_no_work() -> None:
    result = _inspect(_state())
    assert result["error"] is None
    assert result["outputs"] == {
        "release_required": "false",
        "github_required": "false",
        "pypi_required": "false",
    }
    assert [TAGGED, ".version"] in result["reads"]
    assert [TAGGED, "CHANGELOG.md"] in result["reads"]
    assert [HEAD, "CHANGELOG.md"] not in result["reads"]


@pytest.mark.parametrize("existing", ("none", "pypi", "draft"))
def test_unfinished_publication_requires_ci_and_only_missing_targets(
    existing: str,
) -> None:
    state = _state()
    state["tag"] = HEAD if existing == "draft" else None
    if existing == "draft":
        state["release"].update(
            draft=True, target_commitish=HEAD, body=_notes("Head entry.")
        )
        state["assets"] = state["assets"][:1]
    else:
        state["release"] = None
    if existing == "none":
        state["pypi"] = None
    result = _inspect(state)
    assert result["error"] is None
    assert result["outputs"] == {
        "release_required": "true",
        "github_required": "true",
        "pypi_required": str(existing == "none").lower(),
    }
    assert [HEAD, "CHANGELOG.md"] in result["reads"]


@pytest.mark.parametrize(
    "conflict",
    (
        "missing-tag",
        "orphan-tag",
        "moved-tag",
        "source-version",
        "target",
        "notes",
        "prerelease",
        "draft-commit",
        "incomplete-assets",
        "asset-bytes",
        "checksums",
        "yanked",
        "missing-pypi",
    ),
)
def test_publication_conflicts_fail_before_enabling_release(conflict: str) -> None:
    state = _state()
    if conflict == "missing-tag":
        state["tag"] = None
    elif conflict == "orphan-tag":
        state["release"] = None
    elif conflict == "moved-tag":
        state["tag"] = HEAD
    elif conflict == "source-version":
        state["sources"][TAGGED][".version"] = "1.2.2"
    elif conflict == "target":
        state["release"]["target_commitish"] = HEAD
    elif conflict == "notes":
        state["release"]["body"] = _notes("Head entry.")
    elif conflict == "prerelease":
        state["release"]["prerelease"] = True
    elif conflict == "draft-commit":
        state["release"]["draft"] = True
    elif conflict == "incomplete-assets":
        state["assets"].pop()
    elif conflict in {"asset-bytes", "checksums"}:
        index = 0 if conflict == "asset-bytes" else 2
        state["assetBytes"][index] = "conflict"
        state["assets"][index]["size"] = len("conflict")
    elif conflict == "yanked":
        state["pypi"]["urls"][0]["yanked"] = True
    else:
        state["pypi"] = None
    result = _inspect(state)
    assert result["error"]
    assert result["outputs"] == {}


@pytest.mark.parametrize("publication", ("stable", "draft", "prerelease", "absent"))
def test_ci_only_treats_stable_published_versions_as_maintenance(
    tmp_path: Path, publication: str
) -> None:
    state = _state()
    if publication == "absent":
        state["release"] = None
    elif publication != "stable":
        state["release"][publication] = True
    version = tmp_path / ".version"
    version.write_text(VERSION, encoding="ascii")
    script = _block(
        "ci.yml",
        "Resolve published maintenance or unpublished recovery baseline",
        "script",
    )
    result = _execute(script, state, VERSION_PATH=str(version))
    assert result["error"] is None
    assert result["outputs"] == {
        "published_current_version": str(publication == "stable").lower(),
        "unpublished_base_version": "" if publication == "stable" else "1.2.2",
    }


@pytest.mark.parametrize(
    ("base", "published", "expected"),
    (
        (VERSION, "true", ""),
        (
            VERSION,
            "false",
            f"--base-version {VERSION} --unpublished-base-version 1.2.2",
        ),
        ("1.2.2", "false", "--base-version 1.2.2"),
        ("1.2.4", "true", "--base-version 1.2.4"),
    ),
)
def test_ci_passes_version_checks_the_exact_progression_arguments(
    tmp_path: Path, base: str, published: str, expected: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (tmp_path / "base").mkdir()
    (source / ".version").write_text(VERSION, encoding="ascii")
    (tmp_path / "base/.version").write_text(base, encoding="ascii")
    commands = tmp_path / "bin"
    commands.mkdir()
    make = commands / "make"
    make.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n', encoding="ascii")
    make.chmod(0o755)
    completed = subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            _block("ci.yml", "Compare exact base and proposed versions", "run"),
        ],
        cwd=source,
        env={
            **os.environ,
            "PATH": f"{commands}:{os.environ['PATH']}",
            "BASE_REF": TAGGED,
            "ZERO_SHA": "0" * 40,
            "PUBLISHED_CURRENT_VERSION": published,
            "UNPUBLISHED_BASE_VERSION": "1.2.2",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.splitlines() == [
        "version-check",
        "PY=python",
        f"VERSION_ARGS={expected}",
    ]
