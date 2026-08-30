# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Tests for heartbeat-supervised remote process ownership."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shlex
import signal
import sys
from pathlib import Path
from typing import cast

import pytest

from ssh_wrapper.connection import OpenSSHMaster
from ssh_wrapper.errors import SSHError
from ssh_wrapper.remote_process import (
    BoundedTail,
    OwnedRemoteProcess,
    build_remote_supervisor_program,
)


class LocalMux:
    """Execute the fixed remote program through a local noninteractive shell."""

    async def ensure_ready(self) -> None:
        return

    def command_argv(self, remote_program: str) -> list[str]:
        return ["/bin/sh", "-c", remote_program]


async def _wait_for_file(path: Path) -> None:
    for _attempt in range(100):
        if path.is_file():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("remote child did not create its identity file")


def _child_argv(pid_file: Path) -> tuple[str, ...]:
    program = (
        "import os, pathlib, time; "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(60)"
    )
    return (sys.executable, "-c", program)


def test_remote_program_encodes_argv_as_data_once() -> None:
    """Shell metacharacters cannot become supervisor syntax."""
    argv = ("application", "value with spaces", "semi;colon", "$(not-run)")

    command = build_remote_supervisor_program(argv, lease_timeout=45, grace_timeout=5)
    fields = shlex.split(command)
    payload = fields[-1] + "=" * (-len(fields[-1]) % 4)

    assert fields[:2] == ["python3", "-c"]
    assert json.loads(base64.urlsafe_b64decode(payload)) == list(argv)
    assert "semi;colon" not in command
    assert "SSH_WRAPPER_HEARTBEAT_V1" in fields[2]


@pytest.mark.parametrize("argv", ((), ("application\x00hidden",)))
def test_remote_program_rejects_invalid_argv(argv: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="argv is invalid"):
        build_remote_supervisor_program(argv, lease_timeout=45, grace_timeout=5)


def test_remote_process_rejects_nonpositive_timeouts() -> None:
    with pytest.raises(ValueError, match="timeouts must be positive"):
        OwnedRemoteProcess(
            cast(OpenSSHMaster, LocalMux()),
            ("application",),
            heartbeat_interval=0,
            lease_timeout=1,
            grace_timeout=1,
        )


@pytest.mark.asyncio
async def test_remote_process_rejects_use_before_start_and_after_close() -> None:
    remote = OwnedRemoteProcess(
        cast(OpenSSHMaster, LocalMux()),
        ("application",),
        heartbeat_interval=1,
        lease_timeout=1,
        grace_timeout=1,
    )

    assert remote.returncode is None
    with pytest.raises(SSHError) as raised:
        await remote.wait()
    assert raised.value.code == "remote_process_not_started"

    await remote.close()
    await remote.close()
    with pytest.raises(SSHError) as raised:
        await remote.start()
    assert raised.value.code == "remote_process_start_failed"


def test_bounded_tail_keeps_only_final_bytes() -> None:
    tail = BoundedTail(limit=5)
    tail.append(b"abc")
    tail.append(b"defg")

    assert tail.data == b"cdefg"
    assert tail.text() == "cdefg"


@pytest.mark.asyncio
async def test_remote_process_keeps_a_bounded_stdout_prefix(tmp_path: Path) -> None:
    remote = OwnedRemoteProcess(
        cast(OpenSSHMaster, LocalMux()),
        (
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.stdout.write('display-name\\n'); sys.stdout.flush(); "
                "sys.stderr.write('diagnostic-line\\n'); sys.stderr.flush()"
            ),
        ),
        heartbeat_interval=0.05,
        lease_timeout=0.5,
        grace_timeout=0.1,
    )

    await remote.start()
    assert await remote.wait() == 0
    await remote.close()

    assert remote.stdout_head == b"display-name\n"
    assert remote.stderr_tail.data.endswith(b"diagnostic-line\n")


@pytest.mark.asyncio
async def test_owner_eof_terminates_only_the_owned_remote_group(tmp_path: Path) -> None:
    """Closing the lifetime channel reaps the child and preserves unrelated work."""
    pid_file = tmp_path / "owned.pid"
    unrelated = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(60)",
        start_new_session=True,
    )
    remote = OwnedRemoteProcess(
        cast(OpenSSHMaster, LocalMux()),
        _child_argv(pid_file),
        heartbeat_interval=0.05,
        lease_timeout=0.5,
        grace_timeout=0.1,
    )
    try:
        await remote.start()
        await _wait_for_file(pid_file)
        owned_pid = int(pid_file.read_text(encoding="utf-8"))

        await remote.close()
        await remote.close()

        with pytest.raises(ProcessLookupError):
            os.kill(owned_pid, 0)
        os.kill(unrelated.pid, 0)
    finally:
        if unrelated.returncode is None:
            os.killpg(unrelated.pid, signal.SIGKILL)
            await unrelated.wait()


@pytest.mark.asyncio
async def test_lease_expiry_and_malformed_frame_stop_remote_child(
    tmp_path: Path,
) -> None:
    """Both bounded owner loss modes fail closed with stable statuses."""
    for malformed, expected in ((False, 71), (True, 70)):
        pid_file = tmp_path / f"child-{expected}.pid"
        remote = OwnedRemoteProcess(
            cast(OpenSSHMaster, LocalMux()),
            _child_argv(pid_file),
            heartbeat_interval=1,
            lease_timeout=0.15,
            grace_timeout=0.05,
        )
        await remote.start()
        await _wait_for_file(pid_file)
        if malformed:
            assert remote._heartbeat_task is not None
            remote._heartbeat_task.cancel()
            await asyncio.gather(remote._heartbeat_task, return_exceptions=True)
            assert remote.process is not None and remote.process.stdin is not None
            remote.process.stdin.write(b"invalid-frame\n")
            await remote.process.stdin.drain()

        assert await asyncio.wait_for(remote.wait(), timeout=2) == expected
        await remote.close()
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text(encoding="utf-8")), 0)
