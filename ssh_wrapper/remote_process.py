# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Heartbeat-supervised long-lived process over an existing SSH mux."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shlex
import signal
from contextlib import suppress

from .bounded import DEFAULT_TAIL_BYTES, BoundedTail
from .connection import OpenSSHMaster
from .errors import SSHError

__all__ = ["BoundedTail", "OwnedRemoteProcess", "build_remote_supervisor_program"]

HEARTBEAT_FRAME = b"SSH_WRAPPER_HEARTBEAT_V1\n"
DEFAULT_HEAD_BYTES = 4 * 1024
LOCAL_STOP_TIMEOUT = 10.0

# This program receives the child argv as URL-safe base64 JSON. Its stdin is a
# dedicated ownership channel and is never forwarded to the child.
REMOTE_SUPERVISOR = r"""
import base64
import json
import os
import select
import signal
import subprocess
import sys
import time

HEARTBEAT = b"SSH_WRAPPER_HEARTBEAT_V1\n"

def decode_argv(value):
    try:
        padding = "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(value + padding)
        argv = json.loads(raw.decode("utf-8"))
    except Exception:
        raise SystemExit(64)
    if not isinstance(argv, list) or not argv or len(argv) > 256:
        raise SystemExit(64)
    if any(not isinstance(item, str) or "\0" in item for item in argv):
        raise SystemExit(64)
    return argv

def terminate_group(process, grace):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + grace
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()

def main():
    if len(sys.argv) != 4:
        return 64
    try:
        lease = float(sys.argv[1])
        grace = float(sys.argv[2])
    except ValueError:
        return 64
    if lease <= 0 or grace <= 0:
        return 64
    argv = decode_argv(sys.argv[3])
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGHUP, stop)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        child = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        sys.stderr.write("SSH_WRAPPER_REMOTE_ERROR_V1 spawn\n")
        sys.stderr.flush()
        return 72

    sys.stderr.write("SSH_WRAPPER_REMOTE_STARTED_V1\n")
    sys.stderr.flush()
    last_heartbeat = time.monotonic()
    pending = bytearray()
    status = 0
    try:
        while child.poll() is None and not stopping:
            remaining = lease - (time.monotonic() - last_heartbeat)
            if remaining <= 0:
                status = 71
                break
            readable, _, _ = select.select([sys.stdin.buffer], [], [], remaining)
            if not readable:
                status = 71
                break
            chunk = os.read(sys.stdin.fileno(), 4096)
            if not chunk:
                break
            pending.extend(chunk)
            while b"\n" in pending:
                line, _, rest = pending.partition(b"\n")
                pending[:] = rest
                if line + b"\n" != HEARTBEAT:
                    status = 70
                    stopping = True
                    break
                last_heartbeat = time.monotonic()
            if len(pending) >= len(HEARTBEAT):
                status = 70
                break
        if child.poll() is not None:
            return child.returncode
        return status
    finally:
        terminate_group(child, grace)

raise SystemExit(main())
"""


def build_remote_supervisor_program(
    argv: tuple[str, ...], *, lease_timeout: float, grace_timeout: float
) -> str:
    """Encode child argv as data in one fixed remote supervisor command."""
    if not argv or len(argv) > 256 or any("\x00" in item for item in argv):
        raise ValueError("remote child argv is invalid")
    payload = (
        base64.urlsafe_b64encode(
            json.dumps(list(argv), ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        .decode("ascii")
        .rstrip("=")
    )
    return shlex.join(
        (
            "python3",
            "-c",
            REMOTE_SUPERVISOR,
            f"{lease_timeout:g}",
            f"{grace_timeout:g}",
            payload,
        )
    )


class OwnedRemoteProcess:
    """Own one remote process group and its heartbeat channel."""

    def __init__(
        self,
        master: OpenSSHMaster,
        argv: tuple[str, ...],
        *,
        heartbeat_interval: float,
        lease_timeout: float,
        grace_timeout: float,
        tail_bytes: int = DEFAULT_TAIL_BYTES,
    ) -> None:
        if heartbeat_interval <= 0 or lease_timeout <= 0 or grace_timeout <= 0:
            raise ValueError("remote process timeouts must be positive")
        self.master = master
        self.argv = argv
        self.heartbeat_interval = heartbeat_interval
        self.lease_timeout = lease_timeout
        self.grace_timeout = grace_timeout
        self.stdout_tail = BoundedTail(tail_bytes)
        self.stderr_tail = BoundedTail(tail_bytes)
        self.stdout_head = b""
        self.process: asyncio.subprocess.Process | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._drain_tasks: tuple[asyncio.Task[None], ...] = ()
        self._closed = False

    async def _drain(
        self,
        stream: asyncio.StreamReader,
        destination: BoundedTail,
    ) -> None:
        while chunk := await stream.read(4096):
            if (
                destination is self.stdout_tail
                and len(self.stdout_head) < DEFAULT_HEAD_BYTES
            ):
                remaining = DEFAULT_HEAD_BYTES - len(self.stdout_head)
                self.stdout_head += chunk[:remaining]
            destination.append(chunk)

    async def _heartbeat(self) -> None:
        process = self.process
        if process is None or process.stdin is None:
            return
        while process.returncode is None:
            process.stdin.write(HEARTBEAT_FRAME)
            await process.stdin.drain()
            await asyncio.sleep(self.heartbeat_interval)

    async def start(self) -> None:
        """Start through the ready mux and begin draining and heartbeats."""
        if self.process is not None or self._closed:
            raise SSHError(
                "remote_process_start_failed", "remote process can only be started once"
            )
        await self.master.ensure_ready()
        remote_program = build_remote_supervisor_program(
            self.argv,
            lease_timeout=self.lease_timeout,
            grace_timeout=self.grace_timeout,
        )
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.master.command_argv(remote_program),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as error:
            raise SSHError(
                "remote_process_start_failed", "cannot start the remote supervisor"
            ) from error
        if self.process.stdout is None or self.process.stderr is None:
            self.process.kill()
            await self.process.wait()
            raise SSHError(
                "remote_process_start_failed",
                "cannot capture remote supervisor output",
            )
        self._drain_tasks = (
            asyncio.create_task(self._drain(self.process.stdout, self.stdout_tail)),
            asyncio.create_task(self._drain(self.process.stderr, self.stderr_tail)),
        )
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    @property
    def returncode(self) -> int | None:
        """Return the local mux channel status when it has exited."""
        return self.process.returncode if self.process is not None else None

    async def wait(self) -> int:
        """Wait for the mux channel and return its exit status."""
        if self.process is None:
            raise SSHError(
                "remote_process_not_started", "remote process is not started"
            )
        return await self.process.wait()

    async def close(self) -> None:
        """Close ownership, reap the supervisor, and stop local drain tasks."""
        if self._closed:
            return
        self._closed = True
        heartbeat = self._heartbeat_task
        if heartbeat is not None:
            heartbeat.cancel()
            with suppress(
                asyncio.CancelledError, BrokenPipeError, ConnectionResetError
            ):
                await heartbeat

        process = self.process
        if process is not None and process.stdin is not None:
            process.stdin.close()
            with suppress(BrokenPipeError, ConnectionResetError):
                await process.stdin.wait_closed()
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(
                    process.wait(),
                    timeout=self.grace_timeout + LOCAL_STOP_TIMEOUT,
                )
            except TimeoutError:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=LOCAL_STOP_TIMEOUT)
                except TimeoutError:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await process.wait()
        if self._drain_tasks:
            await asyncio.gather(*self._drain_tasks, return_exceptions=True)
