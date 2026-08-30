# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Write and verify the exact SHA-256 inventory for release distributions."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA256 = re.compile(r"[0-9a-f]{64}")


class ChecksumError(ValueError):
    """A checksum inventory is missing, malformed, or unexpected."""


def expected_names(version: str) -> set[str]:
    """Return the two immutable Python distribution names."""
    return {
        f"ssh_wrapper-{version}-py3-none-any.whl",
        f"ssh_wrapper-{version}.tar.gz",
    }


def write(directory: Path, *, version: str) -> Path:
    """Write checksums for exactly the expected wheel and sdist."""
    names = expected_names(version)
    actual = {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    if actual != names:
        raise ChecksumError(
            f"distribution inventory {sorted(actual)} != {sorted(names)}"
        )
    output = directory / "SHA256SUMS.txt"
    output.write_text(
        "".join(
            f"{hashlib.sha256((directory / name).read_bytes()).hexdigest()}  {name}\n"
            for name in sorted(names)
        ),
        encoding="ascii",
    )
    output.chmod(0o644)
    return output


def verify(directory: Path, *, version: str) -> None:
    """Verify the exact checksum file against local bytes."""
    path = directory / "SHA256SUMS.txt"
    expected_inventory = expected_names(version) | {path.name}
    actual_inventory = {
        candidate.name for candidate in directory.iterdir() if candidate.is_file()
    }
    if actual_inventory != expected_inventory:
        raise ChecksumError(
            f"distribution inventory {sorted(actual_inventory)} != "
            f"{sorted(expected_inventory)}"
        )
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except OSError as error:
        raise ChecksumError(f"cannot read SHA256SUMS.txt: {error}") from error
    parsed: dict[str, str] = {}
    for line in lines:
        digest, separator, name = line.partition("  ")
        if not separator or SHA256.fullmatch(digest) is None or not name:
            raise ChecksumError(f"malformed checksum line: {line!r}")
        if name in parsed:
            raise ChecksumError(f"duplicate checksum entry: {name}")
        parsed[name] = digest
    if set(parsed) != expected_names(version):
        raise ChecksumError("checksum inventory differs from release distributions")
    for name, digest in parsed.items():
        candidate = directory / name
        if (
            not candidate.is_file()
            or hashlib.sha256(candidate.read_bytes()).hexdigest() != digest
        ):
            raise ChecksumError(f"checksum mismatch for {name}")


def main() -> int:
    """Write and print the current release checksum inventory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args()
    try:
        version = (arguments.root / ".version").read_text(encoding="utf-8").strip()
        output = write(arguments.directory, version=version)
        verify(arguments.directory, version=version)
    except (ChecksumError, OSError) as error:
        print(f"checksum error: {error}", file=sys.stderr)
        return 1
    print(output.read_text(encoding="ascii"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
