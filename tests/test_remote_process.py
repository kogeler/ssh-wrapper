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
from contextlib import suppress
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


def _is_running(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


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


@pytest.mark.asyncio
@pytest.mark.parametrize("leader_exits", (False, True))
async def test_supervisor_cleans_descendants_even_after_group_leader_exits(
    tmp_path: Path, leader_exits: bool
) -> None:
    leader_file = tmp_path / "leader.pid"
    descendant_file = tmp_path / "descendant.pid"
    descendant = (
        "import os, pathlib, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(descendant_file)!r}).write_text(str(os.getpid())); "
        "time.sleep(60)"
    )
    leader = (
        "import os, pathlib, subprocess, sys, time\n"
        f"pathlib.Path({str(leader_file)!r}).write_text(str(os.getpid()))\n"
        f"subprocess.Popen([sys.executable, '-c', {descendant!r}])\n"
        f"while not pathlib.Path({str(descendant_file)!r}).exists(): time.sleep(0.01)\n"
        + ("raise SystemExit(0)\n" if leader_exits else "time.sleep(60)\n")
    )
    remote = OwnedRemoteProcess(
        cast(OpenSSHMaster, LocalMux()),
        (sys.executable, "-c", leader),
        heartbeat_interval=0.02,
        lease_timeout=0.5,
        grace_timeout=0.1,
    )
    try:
        await remote.start()
        await _wait_for_file(descendant_file)
        descendant_pid = int(descendant_file.read_text())
        if leader_exits:
            assert await asyncio.wait_for(remote.wait(), timeout=1) == 0
        await asyncio.wait_for(remote.close(), timeout=1)
        assert not _is_running(descendant_pid)
    finally:
        if leader_file.exists():
            with suppress(ProcessLookupError):
                os.killpg(int(leader_file.read_text()), signal.SIGKILL)
        if remote.process is not None:
            with suppress(ProcessLookupError):
                os.killpg(remote.process.pid, signal.SIGKILL)
            await remote.process.wait()
        if remote._heartbeat_task is not None:
            remote._heartbeat_task.cancel()
            await asyncio.gather(remote._heartbeat_task, return_exceptions=True)
        await asyncio.gather(*remote._drain_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_supervisor_observes_child_exit_without_waiting_for_next_heartbeat() -> (
    None
):
    remote = OwnedRemoteProcess(
        cast(OpenSSHMaster, LocalMux()),
        (sys.executable, "-c", "raise SystemExit(7)"),
        heartbeat_interval=10,
        lease_timeout=60,
        grace_timeout=0.1,
    )
    try:
        await remote.start()
        assert await asyncio.wait_for(remote.wait(), timeout=1) == 7
    finally:
        await remote.close()


@pytest.mark.parametrize("timeout", (float("nan"), float("inf"), -float("inf")))
def test_remote_timeouts_reject_nonfinite_values(timeout: float) -> None:
    for field in ("heartbeat_interval", "lease_timeout", "grace_timeout"):
        timeouts = {
            "heartbeat_interval": 0.1,
            "lease_timeout": 1.0,
            "grace_timeout": 0.1,
        }
        timeouts[field] = timeout
        with pytest.raises(ValueError):
            OwnedRemoteProcess(cast(OpenSSHMaster, LocalMux()), ("worker",), **timeouts)
    for field in ("lease_timeout", "grace_timeout"):
        timeouts = {"lease_timeout": 1.0, "grace_timeout": 0.1}
        timeouts[field] = timeout
        with pytest.raises(ValueError):
            build_remote_supervisor_program(("worker",), **timeouts)


@pytest.mark.parametrize("limit", (0, -1, True, 1.5))
def test_bounded_storage_rejects_invalid_limits(limit: int) -> None:
    with pytest.raises(ValueError):
        BoundedTail(limit=limit)
    with pytest.raises(ValueError):
        OwnedRemoteProcess(
            cast(OpenSSHMaster, LocalMux()),
            ("worker",),
            heartbeat_interval=1,
            lease_timeout=2,
            grace_timeout=1,
            tail_bytes=limit,
        )


def test_bounded_storage_checks_initial_data_and_mutated_limits() -> None:
    with pytest.raises(ValueError):
        BoundedTail(limit=2, data=b"too long")
    tail = BoundedTail(limit=2, data=b"ok")
    tail.append(b"x" * 100_000 + b"yz")
    assert tail.data == b"yz"
    tail.limit = 0
    with pytest.raises(ValueError):
        tail.append(b"must not become unbounded")


@pytest.mark.asyncio
async def test_remote_start_is_single_use_even_while_readiness_is_pending() -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    class PendingMux(LocalMux):
        async def ensure_ready(self) -> None:
            entered.set()
            await release.wait()

    remote = OwnedRemoteProcess(
        cast(OpenSSHMaster, PendingMux()),
        (sys.executable, "-c", "pass"),
        heartbeat_interval=0.05,
        lease_timeout=1,
        grace_timeout=0.1,
    )
    first = asyncio.create_task(remote.start())
    await entered.wait()
    try:
        with pytest.raises(SSHError, match="only be started once"):
            await asyncio.wait_for(remote.start(), timeout=0.5)
    finally:
        release.set()
        await first
        await remote.close()


@pytest.mark.asyncio
async def test_remote_close_cancels_pending_start_without_spawning() -> None:
    entered = asyncio.Event()

    class PendingMux(LocalMux):
        async def ensure_ready(self) -> None:
            entered.set()
            await asyncio.Event().wait()

    remote = OwnedRemoteProcess(
        cast(OpenSSHMaster, PendingMux()),
        ("worker",),
        heartbeat_interval=1,
        lease_timeout=2,
        grace_timeout=1,
    )
    startup = asyncio.create_task(remote.start())
    await entered.wait()
    await asyncio.wait_for(remote.close(), timeout=1)
    with pytest.raises(asyncio.CancelledError):
        await startup
    assert remote.process is None


@pytest.mark.asyncio
async def test_remote_cancelled_close_still_reaps_child_and_drains(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "owned.pid"
    remote = OwnedRemoteProcess(
        cast(OpenSSHMaster, LocalMux()),
        _child_argv(pid_file),
        heartbeat_interval=0.05,
        lease_timeout=1,
        grace_timeout=0.1,
    )
    await remote.start()
    await _wait_for_file(pid_file)
    closing = asyncio.create_task(remote.close())
    await asyncio.sleep(0)
    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert remote.returncode is not None
    assert all(task.done() for task in remote._drain_tasks)
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
    await remote.close()


@pytest.mark.asyncio
async def test_cancelling_wait_does_not_release_remote_ownership(
    tmp_path: Path,
) -> None:
    pid_file = tmp_path / "owned.pid"
    remote = OwnedRemoteProcess(
        cast(OpenSSHMaster, LocalMux()),
        _child_argv(pid_file),
        heartbeat_interval=0.05,
        lease_timeout=1,
        grace_timeout=0.1,
    )
    await remote.start()
    try:
        await _wait_for_file(pid_file)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(remote.wait(), timeout=0.05)
        assert remote.returncode is None
        os.kill(int(pid_file.read_text()), 0)
        assert remote._heartbeat_task is not None and not remote._heartbeat_task.done()
    finally:
        await remote.close()


@pytest.mark.asyncio
async def test_cancelled_remote_spawn_preserves_time_for_owned_group_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "owned.pid"
    release = asyncio.Event()
    original = asyncio.create_subprocess_exec

    async def delayed_spawn(
        *argv: str, **options: object
    ) -> asyncio.subprocess.Process:
        process = await original(*argv, **options)
        await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    remote = OwnedRemoteProcess(
        cast(OpenSSHMaster, LocalMux()),
        (
            sys.executable,
            "-c",
            "import signal; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            + _child_argv(pid_file)[2],
        ),
        heartbeat_interval=0.05,
        lease_timeout=1,
        grace_timeout=0.4,
    )
    startup = asyncio.create_task(remote.start())
    try:
        await _wait_for_file(pid_file)
        startup.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(startup, timeout=2)
        assert not _is_running(int(pid_file.read_text()))
    finally:
        release.set()
        if pid_file.exists():
            with suppress(ProcessLookupError):
                os.killpg(int(pid_file.read_text()), signal.SIGKILL)
        await asyncio.gather(startup, return_exceptions=True)
        await remote.close()
