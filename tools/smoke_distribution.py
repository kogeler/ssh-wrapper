# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Clean-install, exercise, and strictly type-check a wheel or sdist."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SmokeError(RuntimeError):
    """A distribution failed clean installed-package smoke."""


def _executable(path: Path, *, label: str) -> Path:
    candidate: Path
    if not path.is_absolute() and len(path.parts) == 1:
        located = shutil.which(str(path))
        if located is None:
            raise SmokeError(f"{label} is not available: {path}")
        candidate = Path(located)
    else:
        candidate = path.absolute()
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        raise SmokeError(f"{label} is not executable: {candidate}")
    return candidate


def _run(command: list[str], *, cwd: Path, environment: dict[str, str]) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic"
        raise SmokeError(f"command failed ({completed.returncode}): {detail}")


def _extract_sdist(path: Path, destination: Path) -> Path:
    with tarfile.open(path, mode="r:gz") as archive:
        members = archive.getmembers()
        roots = {
            Path(member.name).parts[0] for member in members if Path(member.name).parts
        }
        if len(roots) != 1 or any(
            member.issym() or member.islnk() or member.isdev() for member in members
        ):
            raise SmokeError("sdist is not a single safe regular source tree")
        archive.extractall(destination, filter="data")
    root = destination / roots.pop()
    if not root.is_dir():
        raise SmokeError("sdist root directory is missing")
    return root


def smoke(
    *,
    kind: str,
    dist_dir: Path,
    python: Path,
    mypy: Path,
    build_python: Path | None,
) -> None:
    """Exercise one artifact kind entirely outside the repository tree."""
    version = (ROOT / ".version").read_text(encoding="utf-8").strip()
    dist_dir = dist_dir.resolve()
    python = _executable(python, label="Python interpreter")
    mypy = _executable(mypy, label="mypy")
    environment = os.environ.copy()
    environment.update(
        {
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "PYTHONHASHSEED": "0",
        }
    )
    environment.pop("PYTHONPATH", None)
    environment.pop("MYPYPATH", None)

    with tempfile.TemporaryDirectory(prefix=f"ssh-wrapper-{kind}-smoke-") as temporary:
        root = Path(temporary)
        artifact: Path
        if kind == "wheel":
            artifact = dist_dir / f"ssh_wrapper-{version}-py3-none-any.whl"
        elif kind == "sdist":
            if build_python is None:
                raise SmokeError("sdist smoke requires --build-python")
            build_python = _executable(build_python, label="build interpreter")
            source_archive = dist_dir / f"ssh_wrapper-{version}.tar.gz"
            source_root = _extract_sdist(source_archive, root / "source")
            built = root / "built"
            built.mkdir()
            _run(
                [
                    str(build_python),
                    "-m",
                    "build",
                    "--no-isolation",
                    "--wheel",
                    "--outdir",
                    str(built),
                    str(source_root),
                ],
                cwd=root,
                environment=environment,
            )
            wheels = tuple(built.glob("*.whl"))
            if (
                len(wheels) != 1
                or wheels[0].name != f"ssh_wrapper-{version}-py3-none-any.whl"
            ):
                raise SmokeError("sdist produced an unexpected wheel inventory")
            artifact = wheels[0]
        else:
            raise SmokeError(f"unsupported distribution kind: {kind}")

        if not artifact.is_file():
            raise SmokeError(f"distribution is missing: {artifact.name}")
        environment_path = root / "environment"
        _run(
            [str(python), "-m", "venv", str(environment_path)],
            cwd=root,
            environment=environment,
        )
        installed_python = environment_path / "bin/python"
        _run(
            [
                str(installed_python),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--no-deps",
                "--no-index",
                str(artifact),
            ],
            cwd=root,
            environment=environment,
        )
        _run(
            [str(installed_python), "-m", "pip", "check"],
            cwd=root,
            environment=environment,
        )

        smoke_program = textwrap.dedent(
            f"""
            import asyncio
            import importlib.metadata
            import importlib.resources
            from pathlib import Path

            import ssh_wrapper
            from ssh_wrapper import (
                SESSION_ENVIRONMENT_VARIABLES,
                BoundedTail,
                ConnectionMode,
                ConnectionSpec,
                ConnectionState,
                OpenSSHMaster,
                OwnedRemoteProcess,
                SSHError,
                SSHMasterSettings,
                __version__,
                build_remote_supervisor_program,
                resolve_session_environment,
            )

            assert set(ssh_wrapper.__all__) == {{
                "SESSION_ENVIRONMENT_VARIABLES",
                "BoundedTail",
                "ConnectionMode",
                "ConnectionSpec",
                "ConnectionState",
                "OpenSSHMaster",
                "OwnedRemoteProcess",
                "SSHError",
                "SSHMasterSettings",
                "__version__",
                "build_remote_supervisor_program",
                "resolve_session_environment",
            }}
            assert __version__ == ssh_wrapper.__version__ == {version!r}
            assert importlib.metadata.version("ssh-wrapper") == {version!r}
            assert importlib.resources.files("ssh_wrapper").joinpath("py.typed").is_file()
            connection = ConnectionSpec.from_alias("example")
            assert connection.mode is ConnectionMode.ALIAS
            assert connection.destination == "example"
            tail = BoundedTail(limit=4)
            tail.append(b"12345")
            assert tail.data == b"2345" and tail.text() == "2345"
            tail.clear()
            assert tail.data == b""
            assert SSHError("example", "message").to_dict() == {{
                "error": "example",
                "message": "message",
            }}
            assert "python3" in build_remote_supervisor_program(
                ("printf", "ok"), lease_timeout=3, grace_timeout=1
            )

            async def close_new_master() -> None:
                master = OpenSSHMaster(
                    SSHMasterSettings(
                        ssh_path=Path("/bin/false"),
                        false_path=Path("/bin/false"),
                        connect_timeout=1,
                    ),
                    connection,
                )
                assert master.state is ConnectionState.NEW
                owned = OwnedRemoteProcess(
                    master,
                    ("printf", "ok"),
                    heartbeat_interval=1,
                    lease_timeout=3,
                    grace_timeout=1,
                )
                assert owned.returncode is None
                await owned.close()
                source = {{name: "set" for name in SESSION_ENVIRONMENT_VARIABLES}}
                resolved = await resolve_session_environment(source)
                assert resolved == source and resolved is not source
                await master.close()
                assert master.state is ConnectionState.CLOSED

            asyncio.run(close_new_master())
            """
        )
        _run(
            [str(installed_python), "-c", smoke_program],
            cwd=root,
            environment=environment,
        )

        consumer = root / "consumer.py"
        consumer.write_text(
            textwrap.dedent(
                """
                from pathlib import Path

                from ssh_wrapper import (
                    SESSION_ENVIRONMENT_VARIABLES,
                    BoundedTail,
                    ConnectionMode,
                    ConnectionSpec,
                    ConnectionState,
                    OpenSSHMaster,
                    OwnedRemoteProcess,
                    SSHError,
                    SSHMasterSettings,
                    __version__,
                    build_remote_supervisor_program,
                    resolve_session_environment,
                )

                connection: ConnectionSpec = ConnectionSpec.from_direct(
                    "127.0.0.1", "remote-user", 22
                )
                mode: ConnectionMode = connection.mode
                state: ConnectionState = ConnectionState.NEW
                settings: SSHMasterSettings = SSHMasterSettings(
                    ssh_path=Path("/bin/false"),
                    false_path=Path("/bin/false"),
                    connect_timeout=1,
                )
                master: OpenSSHMaster = OpenSSHMaster(settings, connection)
                owned: OwnedRemoteProcess = OwnedRemoteProcess(
                    master,
                    ("printf", "ok"),
                    heartbeat_interval=1,
                    lease_timeout=3,
                    grace_timeout=1,
                )
                tail: BoundedTail = BoundedTail()
                tail.append(b"diagnostic")
                variables: tuple[str, ...] = SESSION_ENVIRONMENT_VARIABLES
                version: str = __version__
                supervisor: str = build_remote_supervisor_program(
                    ("printf", "ok"), lease_timeout=3, grace_timeout=1
                )
                error: SSHError = SSHError("example", connection.display_target)
                result: dict[str, object] = error.to_dict()

                async def inspect_lifecycle() -> tuple[dict[str, str], int | None]:
                    environment = await resolve_session_environment(
                        {name: "set" for name in variables}
                    )
                    await owned.close()
                    await master.close()
                    return environment, owned.returncode
                """
            ),
            encoding="utf-8",
        )
        _run(
            [
                str(mypy),
                "--strict",
                "--python-executable",
                str(installed_python),
                str(consumer),
            ],
            cwd=root,
            environment=environment,
        )


def main() -> int:
    """Run installed-package smoke."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("wheel", "sdist"), required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--mypy", type=Path, required=True)
    parser.add_argument("--build-python", type=Path)
    arguments = parser.parse_args()
    try:
        smoke(
            kind=arguments.kind,
            dist_dir=arguments.dist_dir,
            python=arguments.python,
            mypy=arguments.mypy,
            build_python=arguments.build_python,
        )
    except (OSError, SmokeError, tarfile.TarError) as error:
        print(f"{arguments.kind} smoke failed: {error}", file=sys.stderr)
        return 1
    print(f"{arguments.kind} clean-install and strict-type smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
