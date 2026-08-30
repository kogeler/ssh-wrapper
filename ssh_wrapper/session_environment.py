# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Recover a narrow user-session environment for initial SSH authentication."""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

SESSION_ENVIRONMENT_VARIABLES = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
    "SSH_AUTH_SOCK",
    "SSH_ASKPASS",
    "SSH_ASKPASS_REQUIRE",
)
PROBE_OUTPUT_LIMIT = 64 * 1024
PROBE_TIMEOUT = 1.0
PROBE_STOP_TIMEOUT = 0.5
PROBE_READ_SIZE = 4096


@dataclass(frozen=True, slots=True)
class _BoundedProbeOutput:
    data: bytes
    truncated: bool


@dataclass(frozen=True, slots=True)
class _ProbeResult:
    returncode: int
    stdout: _BoundedProbeOutput
    stderr: _BoundedProbeOutput


async def _drain_bounded(
    stream: asyncio.StreamReader, limit: int
) -> _BoundedProbeOutput:
    captured = bytearray()
    truncated = False
    while chunk := await stream.read(PROBE_READ_SIZE):
        remaining = limit - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True
    return _BoundedProbeOutput(bytes(captured), truncated)


async def _terminate_probe(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if process.returncode is not None:
        return
    try:
        await asyncio.wait_for(process.wait(), timeout=PROBE_STOP_TIMEOUT)
        return
    except TimeoutError:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await process.wait()


async def _run_probe(
    executable: Path,
    arguments: tuple[str, ...],
    environment: Mapping[str, str],
) -> _ProbeResult | None:
    try:
        process = await asyncio.create_subprocess_exec(
            str(executable),
            *arguments,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=dict(environment),
            start_new_session=True,
        )
    except OSError:
        return None

    if process.stdout is None or process.stderr is None:
        await _terminate_probe(process)
        return None
    stdout_task = asyncio.create_task(
        _drain_bounded(process.stdout, PROBE_OUTPUT_LIMIT)
    )
    stderr_task = asyncio.create_task(
        _drain_bounded(process.stderr, PROBE_OUTPUT_LIMIT)
    )
    try:
        await asyncio.wait_for(process.wait(), timeout=PROBE_TIMEOUT)
    except TimeoutError:
        await _terminate_probe(process)
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        return None
    except BaseException:
        await _terminate_probe(process)
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise

    _done, pending = await asyncio.wait(
        (stdout_task, stderr_task), timeout=PROBE_STOP_TIMEOUT
    )
    if pending:
        await _terminate_probe(process)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return None
    stdout = stdout_task.result()
    stderr = stderr_task.result()
    return _ProbeResult(process.returncode or 0, stdout, stderr)


def _resolve_optional_program(name: str) -> Path | None:
    resolved = shutil.which(name)
    if resolved is None:
        return None
    try:
        executable = Path(resolved).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not executable.is_file() or not os.access(executable, os.X_OK):
        return None
    return executable


def _runtime_path(output: _BoundedProbeOutput, uid: int) -> Path | None:
    if output.truncated:
        return None
    try:
        lines = output.data.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError:
        return None
    if len(lines) != 1:
        return None
    value = lines[0]
    if not value or value != value.strip() or "\x00" in value:
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        return None
    try:
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, RuntimeError):
        return None
    if not resolved.is_dir() or metadata.st_uid != uid:
        return None
    return resolved


def _parse_systemd_environment(output: _BoundedProbeOutput) -> dict[str, str]:
    if output.truncated:
        return {}
    try:
        text = output.data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return {}
    recovered: dict[str, str] = {}
    allowed = frozenset(SESSION_ENVIRONMENT_VARIABLES)
    for line in text.splitlines():
        name, separator, value = line.partition("=")
        if separator and name in allowed and value and "\x00" not in value:
            recovered[name] = value
    return recovered


async def resolve_session_environment(
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a copy with missing Linux user-session routing values recovered."""
    source = os.environ if base_environment is None else base_environment
    environment = dict(source)
    if sys.platform != "linux" or all(
        environment.get(name) for name in SESSION_ENVIRONMENT_VARIABLES
    ):
        return environment

    loginctl = _resolve_optional_program("loginctl")
    if loginctl is None:
        return environment
    uid = os.getuid()
    runtime_result = await _run_probe(
        loginctl,
        ("show-user", str(uid), "--property=RuntimePath", "--value"),
        environment,
    )
    if runtime_result is None or runtime_result.returncode != 0:
        return environment
    runtime_path = _runtime_path(runtime_result.stdout, uid)
    if runtime_path is None:
        return environment

    systemctl = _resolve_optional_program("systemctl")
    if systemctl is None:
        return environment
    probe_environment = environment.copy()
    probe_environment["XDG_RUNTIME_DIR"] = str(runtime_path)
    probe_environment["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={runtime_path / 'bus'}"
    session_result = await _run_probe(
        systemctl,
        ("--user", "show-environment"),
        probe_environment,
    )
    if session_result is None or session_result.returncode != 0:
        return environment

    for name, value in _parse_systemd_environment(session_result.stdout).items():
        if not environment.get(name):
            environment[name] = value
    return environment
