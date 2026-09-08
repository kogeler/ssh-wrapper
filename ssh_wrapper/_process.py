# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Private cancellation-safe ownership of local subprocess groups."""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Any


async def complete_task[T](task: asyncio.Task[T]) -> T:
    """Finish owned cleanup before propagating even repeated caller cancellation."""
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


async def wait_exit(process: asyncio.subprocess.Process) -> int:
    """Reap the direct child without tying exit detection to inherited pipe EOF."""
    while process.returncode is None:
        await asyncio.sleep(0.01)
    return await process.wait()


def signal_group(process: asyncio.subprocess.Process, signum: int) -> bool:
    """Signal only the new session created for this owned subprocess."""
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        return False
    return True


async def stop_group(process: asyncio.subprocess.Process, grace: float) -> None:
    """Escalate against surviving group members, not just their original leader."""
    if signal_group(process, signal.SIGTERM):
        deadline = asyncio.get_running_loop().time() + grace
        while signal_group(process, 0):
            if asyncio.get_running_loop().time() >= deadline:
                signal_group(process, signal.SIGKILL)
                break
            await asyncio.sleep(0.01)
    await asyncio.wait_for(wait_exit(process), timeout=max(grace, 1.0))


async def finish_tasks(tasks: tuple[asyncio.Task[Any], ...], timeout: float) -> None:
    """Give drains bounded time to reach EOF, then cancel and retrieve every task."""
    if not tasks:
        return
    _done, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _discard(stream: asyncio.StreamReader) -> None:
    while await stream.read(4096):
        pass


async def _reap_cancelled_spawn(
    task: asyncio.Task[asyncio.subprocess.Process],
    owner_close_timeout: float | None,
) -> None:
    try:
        process = await task
    except OSError:
        return
    drains = tuple(
        asyncio.create_task(_discard(stream))
        for stream in (process.stdout, process.stderr)
        if stream is not None
    )
    if process.stdin is not None:
        process.stdin.close()
    try:
        if owner_close_timeout is not None:
            try:
                await asyncio.wait_for(wait_exit(process), timeout=owner_close_timeout)
                return
            except TimeoutError:
                pass
        await stop_group(process, 0.2)
    finally:
        await finish_tasks(drains, 0.5)


async def spawn_owned(
    *argv: str, owner_close_timeout: float | None = None, **options: Any
) -> asyncio.subprocess.Process:
    """Never lose a process handle to cancellation during async process creation."""
    task = asyncio.create_task(
        asyncio.create_subprocess_exec(*argv, **options, start_new_session=True)
    )
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await complete_task(
            asyncio.create_task(_reap_cancelled_spawn(task, owner_close_timeout))
        )
        raise
