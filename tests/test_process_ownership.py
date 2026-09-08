# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Cancellation during process creation must not abandon a local child."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from ssh_wrapper._process import spawn_owned


@pytest.mark.asyncio
async def test_cancellation_during_spawn_recovers_and_reaps_the_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    original = asyncio.create_subprocess_exec
    processes: list[asyncio.subprocess.Process] = []

    async def delayed_spawn(
        *argv: str, **options: object
    ) -> asyncio.subprocess.Process:
        process = await original(*argv, **options)
        processes.append(process)
        entered.set()
        await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    startup = asyncio.create_task(
        spawn_owned(
            sys.executable,
            "-c",
            "import time; time.sleep(60)",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    )
    await entered.wait()
    startup.cancel()
    await asyncio.sleep(0)
    startup.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await startup
    assert len(processes) == 1 and processes[0].returncode is not None
    with pytest.raises(ProcessLookupError):
        os.kill(processes[0].pid, 0)
