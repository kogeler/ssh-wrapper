# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Build exactly one wheel and one normalized sdist without network access."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

if __package__:
    from .normalize_sdist import normalize as normalize_sdist
    from .normalize_wheel import normalize as normalize_wheel
else:
    from normalize_sdist import normalize as normalize_sdist
    from normalize_wheel import normalize as normalize_wheel

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


class BuildError(RuntimeError):
    """The deterministic distribution build failed its boundary."""


def _remove_owned(path: Path, *, root: Path) -> None:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise BuildError(
            f"refusing to remove path outside build root: {path}"
        ) from error
    if resolved == resolved_root:
        raise BuildError("refusing to remove the build root")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def build(*, root: Path, python: Path, output: Path, epoch: int) -> tuple[Path, Path]:
    """Build, normalize, and return the exact wheel and sdist paths."""
    root = root.resolve()
    python = python.absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise BuildError(f"build interpreter is not executable: {python}")
    output = output if output.is_absolute() else root / output
    output = output.resolve()
    try:
        output.relative_to(root)
    except ValueError as error:
        raise BuildError("distribution output must be inside the build root") from error
    if epoch < 315_532_800:
        raise BuildError("SOURCE_DATE_EPOCH must be at or after 1980-01-01")
    try:
        version = (root / ".version").read_text(encoding="utf-8").strip()
    except OSError as error:
        raise BuildError(f"cannot read .version: {error}") from error
    if VERSION_PATTERN.fullmatch(version) is None:
        raise BuildError(".version must contain one stable X.Y.Z value")

    for path in (output, root / "build", root / "ssh_wrapper.egg-info"):
        _remove_owned(path, root=root)
    output.mkdir(parents=True, mode=0o755)

    environment = os.environ.copy()
    environment.update(
        {
            "LC_ALL": "C.UTF-8",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "PYTHONHASHSEED": "0",
            "SOURCE_DATE_EPOCH": str(epoch),
            "TZ": "UTC",
        }
    )
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            str(python),
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(output),
        ],
        cwd=root,
        env=environment,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise BuildError(
            f"distribution build exited with status {completed.returncode}"
        )

    expected_wheel = output / f"ssh_wrapper-{version}-py3-none-any.whl"
    expected_sdist = output / f"ssh_wrapper-{version}.tar.gz"
    actual = {path for path in output.iterdir() if path.is_file()}
    if actual != {expected_wheel, expected_sdist}:
        raise BuildError(
            "unexpected distribution inventory: "
            + ", ".join(sorted(path.name for path in actual))
        )
    normalize_wheel(expected_wheel, epoch=epoch)
    normalize_sdist(expected_sdist, epoch=epoch)
    for path in (expected_wheel, expected_sdist):
        path.chmod(0o644)
    for path in (root / "build", root / "ssh_wrapper.egg-info"):
        _remove_owned(path, root=root)
    return expected_wheel, expected_sdist


def main() -> int:
    """Run the deterministic build."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epoch", type=int, required=True)
    arguments = parser.parse_args()
    try:
        wheel, sdist = build(
            root=arguments.root,
            python=arguments.python,
            output=arguments.output,
            epoch=arguments.epoch,
        )
    except (BuildError, OSError) as error:
        print(f"distribution build failed: {error}", file=sys.stderr)
        return 1
    print(f"Built {wheel.name} and {sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
