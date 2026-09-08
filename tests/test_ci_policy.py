# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Structural evidence for least-privilege repository automation."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
ACTION_REFERENCE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
SHA_REFERENCE = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _all_workflows() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(WORKFLOWS.glob("*.yml"))
    )


def test_workflow_set_is_event_driven_and_every_action_is_sha_pinned() -> None:
    assert {path.name for path in WORKFLOWS.glob("*.yml")} == {
        "ci.yml",
        "dependency-submission.yml",
        "pages.yml",
        "pr-body.yml",
        "release.yml",
    }
    for path in WORKFLOWS.glob("*.yml"):
        content = path.read_text(encoding="utf-8")
        assert "permissions:\n  contents: read" in content, path
        assert "concurrency:" in content, path
        assert "persist-credentials: true" not in content, path
        for reference in ACTION_REFERENCE.findall(content):
            if reference.startswith("./"):
                continue
            assert SHA_REFERENCE.fullmatch(reference), (path, reference)


def test_every_github_hosted_job_uses_ubuntu_26_04() -> None:
    runners = re.findall(r"^\s+runs-on:\s*([^\s#]+)", _all_workflows(), re.MULTILINE)

    assert runners
    assert set(runners) == {"ubuntu-26.04"}
    actionlint = (ROOT / ".github/actionlint.yaml").read_text(encoding="utf-8")
    assert "GitHub-hosted preview label" in actionlint
    assert "    - ubuntu-26.04\n" in actionlint


def test_workflow_write_permissions_are_confined() -> None:
    workflows = {
        path.name: path.read_text(encoding="utf-8") for path in WORKFLOWS.glob("*.yml")
    }
    combined = "\n".join(workflows.values())

    assert combined.count("security-events: write") == 2
    assert workflows["ci.yml"].count("security-events: write") == 1
    assert workflows["release.yml"].count("security-events: write") == 1
    assert combined.count("contents: write") == 2
    assert combined.count("pages: write") == 1
    assert combined.count("id-token: write") == 2
    assert combined.count("pull-requests: write") == 1
    assert "dependency-submission:\n" in workflows["dependency-submission.yml"]
    assert "publish-github:\n" in workflows["release.yml"]
    assert "publish-pypi:\n" in workflows["release.yml"]
    assert "deploy:\n" in workflows["pages.yml"]
    assert "update:\n" in workflows["pr-body.yml"]


def test_ci_preserves_quality_python_package_and_openssh_gates() -> None:
    ci = _workflow("ci.yml")
    for job in (
        "quality:",
        "compatibility:",
        "distribution:",
        "openssh-acceptance:",
        "dependency-review:",
        "codeql:",
        "version:",
    ):
        assert job in ci
    for relationship in (
        "make quality policy PY=python",
        "python-version: ${{ matrix.python }}",
        '          - "3.13"',
        '          - "3.14"',
        "make test-full test-network-block PY=python",
        "make package smoke reproducibility PY=python",
        "make test-acceptance PY=python",
        "make audit PY=python",
        "actions/dependency-review-action@",
        "github/codeql-action/init@",
        "github/codeql-action/analyze@",
        ".artifacts/coverage-report.md",
    ):
        assert relationship in ci
    assert "make ci PY=python" not in ci
    assert "openssh-server=" not in ci and "command -v sshd" not in ci
    assert "push:\n    branches:\n      - main" not in ci
    assert "windows-" not in ci and "macos-" not in ci

    compatibility_job = ci.split("  compatibility:\n", 1)[1].split(
        "\n  distribution:\n", 1
    )[0]
    assert re.findall(
        r'^          - "(3\.[0-9]+)"$', compatibility_job, re.MULTILINE
    ) == [
        "3.13",
        "3.14",
    ]

    dependency_job = ci.split("  dependency-review:\n", 1)[1].split("\n  codeql:\n", 1)[
        0
    ]
    assert not re.search(r"^    if:", dependency_job, re.MULTILINE)
    assert dependency_job.count("make audit PY=python") == 1
    assert "github.event_name == 'pull_request'" in dependency_job
    assert "github.event.pull_request.head.repo.full_name == github.repository" in (
        dependency_job
    )


def test_ci_has_one_owner_per_library_gate_and_no_application_builds() -> None:
    ci = _workflow("ci.yml")
    release = _workflow("release.yml")
    combined = "\n".join((ci, release, (ROOT / "Makefile").read_text(encoding="utf-8")))

    assert ci.count("make quality policy PY=python") == 1
    assert ci.count("make test-full test-network-block PY=python") == 1
    assert ci.count("make package smoke reproducibility PY=python") == 1
    assert ci.count("make test-acceptance PY=python") == 1
    assert ci.count("actions/upload-artifact@") == 1
    assert "if: ${{ inputs.upload_distributions == true }}" in ci
    assert "upload_distributions: true" in release
    assert _all_workflows().count("uses: ./.github/workflows/ci.yml") == 1
    assert _all_workflows().count("upload_distributions: true") == 1
    assert "build-python-distributions:" not in release
    assert "make build smoke-wheel smoke-sdist" not in release
    for marker in (
        "pyinstaller",
        "nuitka",
        "cx_freeze",
        "briefcase",
        "appimage",
        "docker build",
        "cargo build",
        "npm run build",
    ):
        assert marker not in combined.casefold()


def test_pr_body_is_only_pull_request_target_boundary() -> None:
    workflow = _workflow("pr-body.yml")
    combined = _all_workflows()

    assert combined.count("pull_request_target:") == 1
    assert "    paths:\n      - CHANGELOG.md" in workflow
    assert "Check out trusted default branch" in workflow
    assert "github.rest.repos.getContent" in workflow
    assert "1_000_000" in workflow
    assert "github.rest.pulls.update" in workflow
    assert "ref: ${{ github.event.pull_request.head.sha }}" not in workflow
    assert "Pull-request body changed" in workflow
    assert "secrets." not in workflow


def test_version_job_compares_exact_base_and_head() -> None:
    ci = _workflow("ci.yml")

    assert "github.event.pull_request.base.sha" in ci
    assert "github.event.pull_request.head.repo.full_name" in ci
    assert "github.event.pull_request.head.sha" in ci
    assert 'ZERO_SHA: "0000000000000000000000000000000000000000"' in ci
    assert 'base_version="0.0.0"' in ci
    assert "unpublished_base_version" in ci
    assert "published_current_version" in ci
    assert 'elif [[ "$PUBLISHED_CURRENT_VERSION" != "true" ]]' in ci
    assert 'VERSION_ARGS="$args"' in ci


def test_release_reuses_ci_and_shared_python_distributions() -> None:
    ci = _workflow("ci.yml")
    release = _workflow("release.yml")

    assert release.count("uses: ./.github/workflows/ci.yml") == 1
    assert release.count("make build smoke-wheel smoke-sdist") == 0
    assert release.count("actions/upload-artifact@") == 0
    assert ci.count("actions/upload-artifact@") == 1
    assert ci.count("name: python-distributions") == 1
    assert release.count("name: python-distributions") == 2
    assert release.count("actions/download-artifact@") == 2
    assert release.index("Publish with PyPI Trusted Publishing") < release.index(
        "Publish matching GitHub release"
    )
    assert "compression-level: 0" in ci
    assert "retention-days: 1" in ci
    release_ci = release.split("\n  ci:", 1)[1].split("\n  publish-pypi:", 1)[0]
    assert "needs: release-state" in release_ci
    assert "if: needs.release-state.outputs.release_required == 'true'" in release_ci
    assert "release_required: ${{ steps.check.outputs.release_required }}" in release
    assert 'core.setOutput("release_required", String(releaseRequired))' in release
    assert "const releaseCommit = published ? tagCommit : context.sha;" in release
    assert 'read("CHANGELOG.md", releaseCommit)' in release
    assert "paths:" not in release.split("\npermissions:", 1)[0]


def test_release_state_is_exact_and_recovery_is_non_destructive() -> None:
    release = _workflow("release.yml")

    for invariant in (
        "GitHub asset size changed",
        "GitHub asset ${name} conflicts with PyPI",
        "GitHub checksum asset conflicts",
        "Tag ${tagName} points to",
        "Existing release ${tagName} is not an exact draft",
        "Draft asset ${asset.name} conflicts with gated bytes",
        "Final draft asset hash conflicts",
        "target_commitish: target",
        "draft: true",
        "draft: false",
    ):
        assert invariant in release
    assert "deleteReleaseAsset" not in release
    assert "skip-existing" not in release
    assert "git push" not in release
    assert "overwrite" not in release.casefold()


def test_dependency_submission_is_trusted_main_only() -> None:
    workflow = _workflow("dependency-submission.yml")

    assert "push:" in workflow
    assert "pull_request" not in workflow and "workflow_dispatch" not in workflow
    assert '      - "requirements-*.txt"' in workflow
    assert '      - "requirements-*.in"' in workflow
    assert "      - pyproject.toml" in workflow
    assert 'context.ref !== "refs/heads/main"' in workflow
    assert "EXPECTED_REPOSITORY: kogeler/ssh-wrapper" in workflow
    assert workflow.count("contents: write") == 1
    assert "make dependency-snapshot" in workflow
    for lock in ("dev", "docs", "package", "test"):
        assert f'"requirements-{lock}.txt"' in workflow
    assert "POST /repos/{owner}/{repo}/dependency-graph/snapshots" in workflow


def test_pages_validates_prs_and_confines_publish_permissions() -> None:
    pages = _workflow("pages.yml")

    assert "pull_request:" in pages and "push:" in pages
    assert '      - "docs/**"' in pages
    assert pages.count('      - "requirements-docs.in"') == 2
    assert "make docs-audit PY=python" in pages
    assert pages.count("pages: write") == 1
    assert pages.count("id-token: write") == 1
    assert (
        pages.count("github.event_name == 'push' && github.ref == 'refs/heads/main'")
        == 2
    )


def test_codeowners_assigns_entire_repository_to_kogeler() -> None:
    rules = [
        line
        for line in (ROOT / ".github/CODEOWNERS")
        .read_text(encoding="utf-8")
        .splitlines()
        if line and not line.startswith("#")
    ]

    assert rules == ["* @kogeler"]


def test_pypi_publication_uses_oidc_without_stored_credentials() -> None:
    release = _workflow("release.yml")

    assert "https://pypi.org/pypi/" in release
    assert "file.yanked !== false" in release
    assert "environment:\n      name: pypi" in release
    assert release.count("id-token: write") == 1
    assert "pypa/gh-action-pypi-publish@" in release
    assert "packages-dir: dist" in release
    assert 'attestations: "true"' in release
    assert "verify_pypi_release.py --dist-dir dist" in release
    assert "PYPI_TOKEN" not in release
    assert "password:" not in release
    assert "secrets." not in release


def test_mutable_pins_have_executable_owners() -> None:
    workflows = _all_workflows()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert re.search(r'^requires-python = ">=3\.13,<3\.15"$', pyproject, re.MULTILINE)
    assert "CPython 3.13 or 3.14 is required" in makefile
    assert "SOURCE_DATE_EPOCH" in makefile
    assert re.search(r"image: [^\s]+@sha256:[0-9a-f]{64}$", workflows, re.MULTILINE)
    for reference in ACTION_REFERENCE.findall(workflows):
        if not reference.startswith("./"):
            assert SHA_REFERENCE.fullmatch(reference)
    assert "const tagName = `v${version}`;" in _workflow("release.yml")
