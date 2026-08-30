# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Audit every frozen dependency graph against exact reviewed exceptions."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__:
    from .dependency_policy import LOCKS, validate_resolver_bootstrap
else:
    from dependency_policy import LOCKS, validate_resolver_bootstrap

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXCEPTIONS = ROOT / ".github" / "dependency-audit-exceptions.json"
Finding = tuple[str, str, str]


class AuditError(ValueError):
    """Audit data or its exception contract is invalid."""


def normalize(name: str) -> str:
    """Normalize one distribution name."""
    return re.sub(r"[-_.]+", "-", name).casefold()


def load_json(path: Path, *, source: str) -> object:
    """Load JSON with a concise source-specific error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"cannot read {source}: {error}") from error


def findings(report: object) -> frozenset[Finding]:
    """Extract unique package, version, and advisory findings."""
    if not isinstance(report, dict) or not isinstance(report.get("dependencies"), list):
        raise AuditError("pip-audit report must contain a dependencies list")
    result: set[Finding] = set()
    for dependency in report["dependencies"]:
        if not isinstance(dependency, dict):
            raise AuditError("pip-audit dependency entry must be an object")
        name, version, vulnerabilities = (
            dependency.get("name"),
            dependency.get("version"),
            dependency.get("vulns"),
        )
        if (
            not isinstance(name, str)
            or not isinstance(version, str)
            or not isinstance(vulnerabilities, list)
        ):
            raise AuditError("pip-audit dependency entry has an invalid shape")
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict) or not isinstance(
                vulnerability.get("id"), str
            ):
                raise AuditError("pip-audit vulnerability entry has an invalid shape")
            result.add((normalize(name), version, vulnerability["id"]))
    return frozenset(result)


def allowed(config: object) -> frozenset[Finding]:
    """Expand an exact reviewed exception configuration."""
    if (
        not isinstance(config, dict)
        or set(config) != {"exceptions"}
        or not isinstance(config.get("exceptions"), list)
    ):
        raise AuditError("exception config must contain only an exceptions list")
    result: set[Finding] = set()
    for exception in config["exceptions"]:
        if not isinstance(exception, dict) or set(exception) != {
            "package",
            "version",
            "vulnerabilities",
            "reason",
        }:
            raise AuditError("exception entry has an invalid shape")
        package = exception["package"]
        version = exception["version"]
        vulnerabilities = exception["vulnerabilities"]
        reason = exception["reason"]
        if (
            not isinstance(package, str)
            or not package
            or not isinstance(version, str)
            or not version
            or not isinstance(vulnerabilities, list)
            or not vulnerabilities
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise AuditError("exception entry has an invalid shape")
        for identifier in vulnerabilities:
            if not isinstance(identifier, str) or not identifier:
                raise AuditError("exception advisory ID must be non-empty")
            item = (normalize(package), version, identifier)
            if item in result:
                raise AuditError(f"duplicate exception for {format_finding(item)}")
            result.add(item)
    return frozenset(result)


def format_finding(item: Finding) -> str:
    """Format a deterministic diagnostic."""
    return f"{item[0]}=={item[1]}: {item[2]}"


def live_findings() -> frozenset[Finding]:
    """Audit every immutable lock and the exact transient resolver bootstrap."""
    result: set[Finding] = set()

    def audit(label: str, arguments: list[str]) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--strict",
                "--format",
                "json",
                "--disable-pip",
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode not in (0, 1):
            raise AuditError(
                f"pip-audit failed for {label}: "
                f"{completed.stderr.strip() or 'no diagnostic'}"
            )
        try:
            report = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise AuditError(
                f"pip-audit returned invalid JSON for {label}: {error}"
            ) from error
        result.update(findings(report))

    for filename in LOCKS:
        audit(
            filename,
            ["--require-hashes", "--requirement", str(ROOT / filename)],
        )
    bootstrap = validate_resolver_bootstrap(ROOT)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="ssh-wrapper-resolver-", suffix=".txt"
    ) as requirements:
        requirements.writelines(
            f"{name}=={version}\n" for name, version in bootstrap.items()
        )
        requirements.flush()
        audit(
            "resolver bootstrap",
            ["--no-deps", "--requirement", requirements.name],
        )
    return frozenset(result)


def parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    value.add_argument("--report", type=Path)
    return value


def run(arguments: argparse.Namespace) -> None:
    """Compare actual findings with the reviewed set."""
    actual = (
        findings(load_json(arguments.report, source="audit report"))
        if arguments.report
        else live_findings()
    )
    accepted = allowed(load_json(arguments.exceptions, source="exception config"))
    unexpected = sorted(actual - accepted)
    stale = sorted(accepted - actual)
    if unexpected:
        raise AuditError(
            "unexpected vulnerabilities:\n"
            + "\n".join(f"- {format_finding(item)}" for item in unexpected)
        )
    if stale:
        raise AuditError(
            "stale vulnerability exceptions:\n"
            + "\n".join(f"- {format_finding(item)}" for item in stale)
        )
    print(f"Dependency audit accepted {len(actual)} exact reviewed findings")


def main() -> int:
    """Run the helper and return its process status."""
    try:
        run(parser().parse_args())
    except AuditError as error:
        print(f"dependency audit error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
