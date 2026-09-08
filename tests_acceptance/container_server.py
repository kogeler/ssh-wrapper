# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Test-only server ownership; clients and hardware credentials stay on the host."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import re
import sys
import uuid
from pathlib import PurePosixPath
from types import TracebackType
from typing import Literal, Self

from ssh_wrapper._process import complete_task, spawn_owned, stop_group

FIDO_KEY_TYPES = {"sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com"}


def public_authorization(text: str, *, fido: bool) -> str:
    """Strip comments and refuse options, multiple keys, and non-FIDO identities."""
    lines = text.strip().splitlines()
    fields = lines[0].split() if len(lines) == 1 else []
    allowed = FIDO_KEY_TYPES if fido else {"ssh-ed25519"}
    if len(fields) < 2 or fields[0] not in allowed:
        raise ValueError(
            "expected one OpenSSH security-key public key"
            if fido
            else "expected one Ed25519 public key"
        )
    try:
        if not base64.b64decode(fields[1], validate=True):
            raise ValueError("empty public key")
    except (binascii.Error, ValueError) as error:
        raise ValueError("invalid public key encoding") from error
    return f"{fields[0]} {fields[1]}"


class ContainerServer:
    """Own exactly one throwaway server in a private container PID namespace."""

    username = "fixture"
    directory = PurePosixPath("/tmp/ssh-wrapper")

    def __init__(self, authorization: str) -> None:
        self.engine = os.environ.get("SSH_WRAPPER_TEST_CONTAINER", "")
        self.image = os.environ.get("SSH_WRAPPER_TEST_IMAGE", "")
        if not self.engine or not re.fullmatch(r"sha256:[0-9a-f]{64}", self.image):
            raise RuntimeError(
                "run make test-acceptance or make test-fido to prepare the container server"
            )
        self.name = f"ssh-wrapper-acceptance-{uuid.uuid4().hex}"
        debug = os.environ.get("SSH_WRAPPER_TEST_DEBUG", "0")
        if debug not in {"0", "1"}:
            raise ValueError("SSH_WRAPPER_TEST_DEBUG must be 0 or 1")
        self.debug = debug == "1"
        self.authorization = authorization
        self.environment = dict(os.environ)
        # Match the shared Make engine boundary without changing native client prompts.
        self.environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
        self.environment.pop("DBUS_SYSTEM_BUS_ADDRESS", None)
        self.port = 0
        self.host_key = ""
        self._attempted = False
        self._created = False

    def run_argv(self, network: Literal["pasta", "bridge"]) -> tuple[str, ...]:
        """Never mount host paths, agent sockets, token devices, or the checkout."""
        return (
            "run",
            "--detach",
            "--name",
            self.name,
            "--pull=never",
            # Init belongs to the image, never a host catatonit/docker-init mount.
            "--init=false",
            "--read-only",
            "--cap-drop=all",
            "--security-opt=no-new-privileges",
            "--user=10000:10000",
            "--pids-limit=128",
            f"--network={network}",
            "--publish=127.0.0.1::2222",
            "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777",
            "--tmpfs=/run/sshd:rw,nosuid,nodev,noexec,size=1m,mode=0755",
            "--env",
            f"SSH_WRAPPER_AUTHORIZED_KEY={self.authorization}",
            self.image,
        )

    async def _call(
        self, *argv: str, check: bool = True, merge_stderr: bool = False
    ) -> str:
        process = await spawn_owned(
            self.engine,
            *(("--log-level=debug",) if self.debug else ()),
            *argv,
            env=self.environment,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
            if merge_stderr
            else asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        finally:
            if process.returncode is None:
                await complete_task(asyncio.create_task(stop_group(process, 0.2)))
        if self.debug and stderr:
            print(stderr.decode(errors="replace")[-4096:], file=sys.stderr, end="")
        if check and process.returncode:
            diagnostic = (stdout if stderr is None else stderr).decode(
                errors="replace"
            )[-4096:]
            raise RuntimeError(f"container {argv[0]} failed: {diagnostic}")
        return stdout.decode("utf-8")

    async def _network_mode(self) -> Literal["pasta", "bridge"]:
        """Use per-container pasta for rootless Podman, not its shared bridge."""
        try:
            info = json.loads(await self._call("info", "--format", "{{json .}}"))
            if not isinstance(info, dict):
                raise TypeError("container engine info must be an object")
        except (json.JSONDecodeError, TypeError) as error:
            raise RuntimeError("container engine info is not a JSON object") from error
        if "host" in info:
            host = info["host"]
            security = host.get("security") if isinstance(host, dict) else None
            if not isinstance(security, dict) or security.get("rootless") is not True:
                raise RuntimeError(
                    "Podman acceptance requires rootless mode; run Make without sudo"
                )
            return "pasta"
        if info.get("OSType") == "linux" and isinstance(info.get("ServerVersion"), str):
            return "bridge"
        raise RuntimeError(
            "container engine info does not identify Linux Podman or Docker"
        )

    async def __aenter__(self) -> Self:
        network = await self._network_mode()
        self._attempted = True
        try:
            await self._call(*self.run_argv(network))
            self._created = True
            published = await self._call("port", self.name, "2222/tcp")
            match = re.fullmatch(r"127\.0\.0\.1:([0-9]+)\s*", published)
            if match is None or not 1 <= int(match[1]) <= 65535:
                log = await self.logs()
                raise RuntimeError(
                    f"container SSH port was not bound exclusively to loopback: {published!r}; {log[-4096:]}"
                )
            self.port = int(match[1])
            deadline = asyncio.get_running_loop().time() + 15
            while True:
                log = await self.logs()
                key = re.search(
                    r"^SSH_WRAPPER_HOST_KEY (ssh-ed25519 [A-Za-z0-9+/=]+)\r?$",
                    log,
                    re.MULTILINE,
                )
                if key is not None and "Server listening on " in log:
                    self.host_key = public_authorization(key[1], fido=False)
                    return self
                running = await self._call(
                    "inspect", "--format", "{{.State.Running}}", self.name
                )
                if (
                    running.strip() != "true"
                    or asyncio.get_running_loop().time() >= deadline
                ):
                    raise RuntimeError(
                        f"container SSH server did not become ready: {log[-4096:]}"
                    )
                await asyncio.sleep(0.05)
        except BaseException:
            await complete_task(asyncio.create_task(self.close()))
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await complete_task(asyncio.create_task(self.close()))

    async def close(self) -> None:
        if self._attempted:
            # A timed-out or cancelled run can create the container before losing
            # its CLI handle. The unique owned name is known before that await.
            await self._call("rm", "--force", self.name, check=self._created)
            self._attempted = False

    async def logs(self) -> str:
        return await self._call("logs", self.name, merge_stderr=True)

    async def python(self, code: str, *arguments: str) -> str:
        return await self._call("exec", self.name, "python3", "-c", code, *arguments)

    async def wait_for_pid_file(self, path: PurePosixPath) -> int:
        return int(
            await self.python(
                "import pathlib,sys,time\n"
                "path=pathlib.Path(sys.argv[1]); deadline=time.monotonic()+5\n"
                "while not path.is_file() or not path.stat().st_size:\n"
                " if time.monotonic() >= deadline: raise RuntimeError('PID file not created')\n"
                " time.sleep(0.05)\n"
                "pid=int(path.read_text()); assert pid > 1; print(pid)\n",
                str(path),
            )
        )

    async def process_group(self, pid: int) -> int:
        return int(
            await self.python(
                "import os,sys; print(os.getpgid(int(sys.argv[1])))", str(pid)
            )
        )

    async def signal(self, pid: int, signum: int) -> None:
        if pid <= 1:
            raise ValueError("refusing to signal the container init")
        await self.python(
            "import os,sys; os.kill(int(sys.argv[1]), int(sys.argv[2]))",
            str(pid),
            str(signum),
        )

    async def wait_for_pid_exit(self, pid: int) -> None:
        await self.python(
            "import os,sys,time\n"
            "pid=int(sys.argv[1]); deadline=time.monotonic()+5\n"
            "while True:\n"
            " try: os.kill(pid, 0)\n"
            " except ProcessLookupError: break\n"
            " if time.monotonic() >= deadline: raise RuntimeError('owned process did not exit')\n"
            " time.sleep(0.05)\n",
            str(pid),
        )
