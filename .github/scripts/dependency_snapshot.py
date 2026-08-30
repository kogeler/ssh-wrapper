# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Build GitHub dependency-submission manifests from committed hash locks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(DEFAULT_ROOT))

from tools.dependency_policy import PolicyError, build_manifests


def run(root: Path, output: Path) -> None:
    """Write one deterministic offline dependency snapshot."""
    payload = {"manifests": build_manifests(root.resolve())}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "Dependency snapshot generated: "
        + ", ".join(
            f"{name}={len(manifest['resolved'])}"
            for name, manifest in payload["manifests"].items()
        )
    )


def main() -> int:
    """Run the snapshot helper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        run(arguments.root, arguments.output)
    except (OSError, PolicyError) as error:
        print(f"dependency snapshot error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
