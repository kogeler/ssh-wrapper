# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from ssh_wrapper import session_environment

LOGINCTL = r"""#!__PYTHON__
import os
import sys

expected = [
    "show-user",
    os.environ["FAKE_EXPECTED_UID"],
    "--property=RuntimePath",
    "--value",
]
if sys.argv[1:] != expected:
    raise SystemExit(91)
if os.environ.get("FAKE_LOGINCTL_PID"):
    with open(os.environ["FAKE_LOGINCTL_PID"], "w", encoding="utf-8") as output:
        output.write(str(os.getpid()))
if os.environ.get("FAKE_LOGINCTL_SLEEP"):
    import time
    time.sleep(60)
if os.environ.get("FAKE_RUNTIME_PATH"):
    print(os.environ["FAKE_RUNTIME_PATH"])
raise SystemExit(int(os.environ.get("FAKE_LOGINCTL_STATUS", "0")))
"""

SYSTEMCTL = r"""#!__PYTHON__
import json
import os
import sys
import time
from pathlib import Path

if sys.argv[1:] != ["--user", "show-environment"]:
    raise SystemExit(92)
if os.environ.get("FAKE_SYSTEMCTL_RECORD"):
    Path(os.environ["FAKE_SYSTEMCTL_RECORD"]).write_text(
        json.dumps({
            "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR"),
            "DBUS_SESSION_BUS_ADDRESS": os.environ.get("DBUS_SESSION_BUS_ADDRESS"),
            "ORIGINAL": os.environ.get("ORIGINAL"),
        }),
        encoding="utf-8",
    )
if os.environ.get("FAKE_SYSTEMCTL_PID"):
    Path(os.environ["FAKE_SYSTEMCTL_PID"]).write_text(
        str(os.getpid()), encoding="utf-8"
    )
if os.environ.get("FAKE_SYSTEMCTL_SLEEP"):
    time.sleep(60)
if os.environ.get("FAKE_SYSTEMD_OUTPUT"):
    sys.stdout.buffer.write(Path(os.environ["FAKE_SYSTEMD_OUTPUT"]).read_bytes())
raise SystemExit(int(os.environ.get("FAKE_SYSTEMCTL_STATUS", "0")))
"""


def write_executable(path: Path, content: str) -> None:
    path.write_text(content.replace("__PYTHON__", sys.executable), encoding="utf-8")
    path.chmod(0o755)


def install_probes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    programs = tmp_path / "programs"
    programs.mkdir()
    write_executable(programs / "loginctl", LOGINCTL)
    write_executable(programs / "systemctl", SYSTEMCTL)
    monkeypatch.setenv("PATH", str(programs))
    return programs


def probe_environment(
    tmp_path: Path,
    runtime_path: str,
    systemd_output: bytes = b"",
) -> dict[str, str]:
    output_path = tmp_path / "systemd.environment"
    output_path.write_bytes(systemd_output)
    return {
        "PATH": str(tmp_path / "programs"),
        "ORIGINAL": "preserved",
        "FAKE_EXPECTED_UID": str(os.getuid()),
        "FAKE_RUNTIME_PATH": runtime_path,
        "FAKE_SYSTEMD_OUTPUT": str(output_path),
    }


@pytest.mark.asyncio
async def test_complete_inherited_environment_does_not_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inherited = {
        name: f"inherited-{index}"
        for index, name in enumerate(session_environment.SESSION_ENVIRONMENT_VARIABLES)
    }

    def unexpected_probe(_name: str) -> Path | None:
        raise AssertionError("complete environment must not resolve probes")

    monkeypatch.setattr(
        session_environment, "_resolve_optional_program", unexpected_probe
    )

    assert await session_environment.resolve_session_environment(inherited) == inherited


@pytest.mark.asyncio
async def test_recovers_only_allowlisted_missing_values_with_inherited_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_probes(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    record = tmp_path / "probe.json"
    output = b"\n".join(
        (
            b"DISPLAY=:systemd",
            b"WAYLAND_DISPLAY=wayland-7",
            f"XDG_RUNTIME_DIR={runtime}".encode(),
            f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus".encode(),
            b"SSH_AUTH_SOCK=/session/agent.sock",
            b"PATH=/untrusted/path",
            b"API_TOKEN=must-not-be-imported",
        )
    )
    inherited = probe_environment(tmp_path, str(runtime), output)
    inherited.update(
        {
            "DISPLAY": ":inherited",
            "FAKE_SYSTEMCTL_RECORD": str(record),
        }
    )
    before = inherited.copy()
    process_environment_before = os.environ.copy()

    recovered = await session_environment.resolve_session_environment(inherited)

    assert recovered["DISPLAY"] == ":inherited"
    assert recovered["WAYLAND_DISPLAY"] == "wayland-7"
    assert recovered["SSH_AUTH_SOCK"] == "/session/agent.sock"
    assert recovered["PATH"] == inherited["PATH"]
    assert "API_TOKEN" not in recovered
    assert inherited == before
    assert os.environ == process_environment_before
    probe = json.loads(record.read_text(encoding="utf-8"))
    assert probe == {
        "XDG_RUNTIME_DIR": str(runtime),
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime}/bus",
        "ORIGINAL": "preserved",
    }


@pytest.mark.asyncio
async def test_empty_and_malformed_systemd_assignments_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_probes(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    inherited = probe_environment(
        tmp_path,
        str(runtime),
        b"DISPLAY=\nBROKEN\n=unnamed\nSSH_AUTH_SOCK=/agent=detail\n"
        b"WAYLAND_DISPLAY=wayland-2\x00hidden\n",
    )

    recovered = await session_environment.resolve_session_environment(inherited)

    assert "DISPLAY" not in recovered
    assert "BROKEN" not in recovered
    assert recovered["SSH_AUTH_SOCK"] == "/agent=detail"
    assert "WAYLAND_DISPLAY" not in recovered


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_kind", ["relative", "missing", "file", "multiple"])
async def test_invalid_runtime_paths_are_rejected(
    runtime_kind: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_probes(tmp_path, monkeypatch)
    if runtime_kind == "relative":
        value = "relative/runtime"
    elif runtime_kind == "missing":
        value = str(tmp_path / "missing")
    elif runtime_kind == "file":
        candidate = tmp_path / "runtime-file"
        candidate.write_text("not a directory", encoding="utf-8")
        value = str(candidate)
    else:
        candidate = tmp_path / "runtime"
        candidate.mkdir()
        value = f"{candidate}\n{candidate}"
    record = tmp_path / "systemctl-ran"
    inherited = probe_environment(tmp_path, value, b"DISPLAY=:recovered\n")
    inherited["FAKE_SYSTEMCTL_RECORD"] = str(record)

    assert await session_environment.resolve_session_environment(inherited) == inherited
    assert not record.exists()


@pytest.mark.asyncio
async def test_wrong_owner_runtime_path_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_probes(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    actual_uid = os.getuid()
    inherited = probe_environment(tmp_path, str(runtime), b"DISPLAY=:recovered\n")
    inherited["FAKE_EXPECTED_UID"] = str(actual_uid + 1)
    monkeypatch.setattr(session_environment.os, "getuid", lambda: actual_uid + 1)

    assert await session_environment.resolve_session_environment(inherited) == inherited


@pytest.mark.asyncio
async def test_missing_probe_executables_are_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_path = tmp_path / "empty"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    inherited = {"PATH": str(empty_path), "ORIGINAL": "preserved"}

    assert await session_environment.resolve_session_environment(inherited) == inherited


@pytest.mark.asyncio
async def test_non_executable_probe_is_a_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    programs = tmp_path / "programs"
    programs.mkdir()
    loginctl = programs / "loginctl"
    loginctl.write_text("not executable", encoding="utf-8")
    loginctl.chmod(0o600)
    monkeypatch.setenv("PATH", str(programs))
    inherited = {"PATH": str(programs), "ORIGINAL": "preserved"}

    assert await session_environment.resolve_session_environment(inherited) == inherited


@pytest.mark.asyncio
@pytest.mark.parametrize("probe", ["loginctl", "systemctl"])
async def test_probe_command_failure_is_a_noop(
    probe: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_probes(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    inherited = probe_environment(tmp_path, str(runtime), b"DISPLAY=:recovered\n")
    inherited[f"FAKE_{probe.upper()}_STATUS"] = "7"

    assert await session_environment.resolve_session_environment(inherited) == inherited


@pytest.mark.asyncio
@pytest.mark.parametrize("probe", ["loginctl", "systemctl"])
async def test_probe_timeout_reaps_the_child(
    probe: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_probes(tmp_path, monkeypatch)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    pid_path = tmp_path / f"{probe}.pid"
    inherited = probe_environment(tmp_path, str(runtime), b"DISPLAY=:recovered\n")
    inherited[f"FAKE_{probe.upper()}_PID"] = str(pid_path)
    inherited[f"FAKE_{probe.upper()}_SLEEP"] = "1"
    monkeypatch.setattr(session_environment, "PROBE_TIMEOUT", 0.1)

    assert await session_environment.resolve_session_environment(inherited) == inherited
    pid = int(pid_path.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.asyncio
async def test_probe_output_is_bounded_and_drained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = tmp_path / "large-probe"
    write_executable(
        program,
        r"""#!__PYTHON__
import sys
sys.stdout.buffer.write(b"o" * 100_000)
sys.stderr.buffer.write(b"e" * 100_000)
""",
    )
    monkeypatch.setattr(session_environment, "PROBE_OUTPUT_LIMIT", 1024)

    result = await session_environment._run_probe(program, (), os.environ)

    assert result is not None and result.returncode == 0
    assert result.stdout.data == b"o" * 1024
    assert result.stderr.data == b"e" * 1024
    assert result.stdout.truncated is True
    assert result.stderr.truncated is True


@pytest.mark.asyncio
async def test_non_linux_environment_is_a_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inherited = {"ORIGINAL": "preserved"}
    monkeypatch.setattr(session_environment.sys, "platform", "darwin")

    def unexpected_probe(_name: str) -> Path | None:
        raise AssertionError("non-Linux environment must not resolve probes")

    monkeypatch.setattr(
        session_environment, "_resolve_optional_program", unexpected_probe
    )

    assert await session_environment.resolve_session_environment(inherited) == inherited
