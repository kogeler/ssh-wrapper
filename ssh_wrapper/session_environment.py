# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Recover a narrow user-session environment for initial SSH authentication."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ._process import complete_task, finish_tasks, spawn_owned, stop_group, wait_exit

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
    await stop_group(process, PROBE_STOP_TIMEOUT)


async def _run_probe(
    executable: Path,
    arguments: tuple[str, ...],
    environment: Mapping[str, str],
) -> _ProbeResult | None:
    try:
        process = await spawn_owned(
            str(executable),
            *arguments,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=dict(environment),
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

    async def cleanup() -> None:
        try:
            await _terminate_probe(process)
        finally:
            await finish_tasks((stdout_task, stderr_task), PROBE_STOP_TIMEOUT)

    try:
        async with asyncio.timeout(PROBE_TIMEOUT):
            await wait_exit(process)
            await asyncio.gather(stdout_task, stderr_task)
        return _ProbeResult(
            process.returncode or 0, stdout_task.result(), stderr_task.result()
        )
    except TimeoutError:
        return None
    finally:
        await complete_task(asyncio.create_task(cleanup()))


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


def _parse_systemd_environment(
    output: _BoundedProbeOutput, *, json_output: bool = False
) -> dict[str, str]:
    if output.truncated:
        return {}
    try:
        text = output.data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return {}
    recovered: dict[str, str] = {}
    allowed = frozenset(SESSION_ENVIRONMENT_VARIABLES)
    if json_output:
        try:
            document = json.loads(text)
        except (ValueError, RecursionError):
            return {}
        if not isinstance(document, dict):
            return {}
        for name, value in document.items():
            if (
                name not in allowed
                or not isinstance(value, str)
                or not value
                or "\x00" in value
            ):
                continue
            try:
                value.encode("utf-8")
            except UnicodeError:
                continue
            recovered[name] = value
        return recovered
    for line in text.splitlines():
        name, separator, value = line.partition("=")
        if not separator or name not in allowed or value.startswith("$'"):
            continue
        try:
            fields = shlex.split(value)
        except ValueError:
            continue
        if len(fields) == 1 and fields[0] and "\x00" not in fields[0]:
            recovered[name] = fields[0]
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
        ("--user", "show-environment", "--output=json"),
        probe_environment,
    )
    json_output = True
    if session_result is not None and session_result.returncode != 0:
        # Older systemd versions do not support JSON for show-environment.
        json_output = False
        session_result = await _run_probe(
            systemctl, ("--user", "show-environment"), probe_environment
        )
    if session_result is None or session_result.returncode != 0:
        return environment

    recovered = _parse_systemd_environment(
        session_result.stdout, json_output=json_output
    )
    runtime_value = recovered.get("XDG_RUNTIME_DIR")
    if (
        runtime_value is not None
        and _runtime_path(
            _BoundedProbeOutput(runtime_value.encode("utf-8"), False), uid
        )
        is None
    ):
        del recovered["XDG_RUNTIME_DIR"]
    for name, value in recovered.items():
        if not environment.get(name):
            environment[name] = value
    return environment
