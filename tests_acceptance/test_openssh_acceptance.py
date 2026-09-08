# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Shared live scenario: native host client and one isolated container server."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from ssh_wrapper import (
    ConnectionSpec,
    ConnectionState,
    OpenSSHMaster,
    OwnedRemoteProcess,
    SSHError,
    SSHMasterSettings,
)
from ssh_wrapper.connection import MASTER_STDERR_TAIL_BYTES, MAX_CONTROL_PATH_BYTES
from tests_acceptance.container_server import ContainerServer, public_authorization

pytestmark = [
    pytest.mark.acceptance,
    pytest.mark.skipif(
        sys.platform != "linux", reason="OpenSSH acceptance is Linux-only"
    ),
]


def _program(name: str) -> Path:
    resolved = shutil.which(name)
    if resolved is None:
        pytest.fail(
            f"required OpenSSH client command is unavailable: {name}", pytrace=False
        )
    return Path(resolved).resolve(strict=True)


def _generate_key(keygen: Path, destination: Path) -> None:
    completed = subprocess.run(
        [str(keygen), "-q", "-t", "ed25519", "-N", "", "-f", str(destination)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode:
        raise AssertionError("ssh-keygen failed for an ephemeral acceptance key")


@pytest.mark.asyncio
async def test_real_openssh_one_auth_mux_and_owned_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove one auth, mux-only channels, no fallback, and selective cleanup."""
    await _exercise_openssh(tmp_path, monkeypatch)


async def _exercise_openssh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fido_identity: Path | None = None,
) -> None:
    """Use identical lifecycle assertions for ephemeral and opt-in hardware keys."""

    ssh = _program("ssh")
    false = _program("false")
    if fido_identity is None:
        monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
        monkeypatch.delenv("SSH_AGENT_PID", raising=False)
    client_key = tmp_path / (
        "client-fido" if fido_identity is not None else "client-ed25519"
    )
    if fido_identity is None:
        _generate_key(_program("ssh-keygen"), client_key)
    else:
        client_key.symlink_to(fido_identity)
        Path(f"{client_key}.pub").symlink_to(Path(f"{fido_identity}.pub"))
    public_key = Path(f"{client_key}.pub")
    authorization = public_authorization(
        public_key.read_text(encoding="utf-8"), fido=fido_identity is not None
    )
    async with ContainerServer(authorization) as server:
        await _exercise_client(
            tmp_path,
            server,
            ssh=ssh,
            false=false,
            client_key=client_key,
            fido=fido_identity is not None,
        )


async def _exercise_client(
    tmp_path: Path,
    server: ContainerServer,
    *,
    ssh: Path,
    false: Path,
    client_key: Path,
    fido: bool,
) -> None:
    """Keep the existing one-auth/mux/cleanup assertions common to both gates."""
    # Prove that the image-owned PID 1 reaps orphans without host init injection.
    # This uses the existing container control channel, not another SSH auth.
    await server.python(
        "import os,pathlib,time\n"
        "assert pathlib.Path('/proc/1/comm').read_text().strip() == 'tini'\n"
        "read_fd,write_fd=os.pipe(); parent=os.fork()\n"
        "if parent == 0:\n"
        " os.close(read_fd); child=os.fork()\n"
        " if child == 0:\n"
        "  os.close(write_fd); time.sleep(0.1); os._exit(0)\n"
        " os.write(write_fd,str(child).encode()); os._exit(0)\n"
        "os.close(write_fd); orphan=int(os.read(read_fd,64)); os.close(read_fd)\n"
        "os.waitpid(parent,0); deadline=time.monotonic()+5\n"
        "while pathlib.Path(f'/proc/{orphan}').exists():\n"
        " if time.monotonic() >= deadline: raise RuntimeError('container init did not reap orphan')\n"
        " time.sleep(0.05)\n"
    )
    known_hosts = tmp_path / "known_hosts"
    client_config = tmp_path / "ssh_config"
    wrapper = tmp_path / "isolated-ssh"
    known_hosts.write_text(
        f"[127.0.0.1]:{server.port} {server.host_key}\n", encoding="ascii"
    )
    known_hosts.chmod(0o600)

    client_config.write_text(
        "\n".join(
            (
                "Host *",
                '  IdentityFile "'
                + str(client_key)
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("%", "%%")
                + '"',
                "  IdentitiesOnly yes",
                "  IdentityAgent none"
                if not fido
                else "  # Use native local FIDO/agent authentication",
                "  AddKeysToAgent no",
                '  UserKnownHostsFile "'
                + str(known_hosts)
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("%", "%%")
                + '"',
                "  GlobalKnownHostsFile /dev/null",
                "  StrictHostKeyChecking yes",
                "  UpdateHostKeys no",
                "  CheckHostIP no",
                "  PasswordAuthentication no",
                "  KbdInteractiveAuthentication no",
                "  HostbasedAuthentication no",
                "  GSSAPIAuthentication no",
                "  ProxyCommand none",
                "  ForkAfterAuthentication yes",
                "  StdinNull yes",
                "  SessionType none",
                "  Tunnel point-to-point",
                "  LogLevel DEBUG3",
                "",
            )
        ),
        encoding="utf-8",
    )
    wrapper.write_text(
        f"#!/bin/sh\nset -eu\nexec {shlex.quote(str(ssh))} "
        f'-F {shlex.quote(str(client_config))} "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o700)

    runtime_base = Path(tempfile.mkdtemp(prefix="swa-"))
    # Exercise literal percent tokens at the longest safe native mux pathname.
    runtime_prefix = "sw%h" + "x" * (
        MAX_CONTROL_PATH_BYTES
        - len(os.fsencode(runtime_base))
        - len(str(os.getuid()))
        - 24
    )
    master = OpenSSHMaster(
        SSHMasterSettings(
            ssh_path=wrapper,
            false_path=false,
            connect_timeout=120 if fido else 8,
            server_alive_interval=2,
            server_alive_count_max=2,
            runtime_prefix=runtime_prefix,
        ),
        ConnectionSpec.from_direct("127.0.0.1", server.username, server.port),
        runtime_base=runtime_base,
    )
    unrelated_channel: asyncio.subprocess.Process | None = None
    unrelated_pid: int | None = None
    owned: OwnedRemoteProcess | None = None
    command: asyncio.subprocess.Process | None = None
    fallback: asyncio.subprocess.Process | None = None
    try:
        if not fido:
            assert "SSH_AUTH_SOCK" not in os.environ
            assert "IdentityAgent none" in client_config.read_text(encoding="utf-8")
        else:
            print(
                "FIDO: container server is ready; starting one authentication. Approve the native prompt/PIN and touch the key when requested; no secrets go through this test.",
                flush=True,
            )
        await master.start()
        assert master.state is ConnectionState.READY
        assert master.process is not None
        assert master.control_path is not None
        assert "%h" in str(master.control_path)
        assert len(os.fsencode(master.control_path)) + 17 < 108
        first_master_pid = master.process.pid
        assert 0 < len(master._stderr_tail.data) <= MASTER_STDERR_TAIL_BYTES

        command = await asyncio.create_subprocess_exec(
            *master.command_argv("printf 'mux-ok\\n'"),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _stderr = await asyncio.wait_for(command.communicate(), timeout=5)
        assert command.returncode == 0 and stdout == b"mux-ok\n"
        assert master.process.pid == first_master_pid

        unrelated_pid_file = server.directory / "unrelated.pid"
        unrelated_program = shlex.join(
            (
                "python3",
                "-c",
                (
                    "import os,sys,time; "
                    "open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)"
                ),
                str(unrelated_pid_file),
            )
        )
        unrelated_channel = await asyncio.create_subprocess_exec(
            *master.command_argv(unrelated_program),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        unrelated_pid = await server.wait_for_pid_file(unrelated_pid_file)

        owned_pid_file = server.directory / "owned.pid"
        owned = OwnedRemoteProcess(
            master,
            (
                "python3",
                "-c",
                (
                    "import os,sys,time; "
                    "open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(60)"
                ),
                str(owned_pid_file),
            ),
            heartbeat_interval=0.05,
            lease_timeout=0.5,
            grace_timeout=0.2,
            tail_bytes=512,
        )
        await owned.start()
        owned_pid = await server.wait_for_pid_file(owned_pid_file)
        assert await server.process_group(owned_pid) == owned_pid
        await owned.close()
        await server.wait_for_pid_exit(owned_pid)
        await server.signal(unrelated_pid, 0)
        assert len(owned.stdout_tail.data) <= 512
        assert len(owned.stderr_tail.data) <= 512

        await server.signal(unrelated_pid, signal.SIGTERM)
        await server.wait_for_pid_exit(unrelated_pid)
        await asyncio.wait_for(unrelated_channel.wait(), timeout=5)
        unrelated_channel = None
        unrelated_pid = None

        assert master.process is not None
        os.killpg(master.process.pid, signal.SIGTERM)
        await asyncio.wait_for(master.process.wait(), timeout=5)
        with pytest.raises(SSHError) as lost:
            await master.ensure_ready()
        assert lost.value.code == "connection_lost"
        assert str(tmp_path) not in lost.value.message

        fallback = await asyncio.create_subprocess_exec(
            *master.command_argv("true"),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(fallback.communicate(), timeout=5)
        assert fallback.returncode != 0
        await asyncio.sleep(0.2)
        log = await server.logs()
        assert (
            sum(line.startswith("Connection from ") for line in log.splitlines()) == 1
        )
        assert sum("Accepted publickey for " in line for line in log.splitlines()) == 1
    finally:
        if owned is not None:
            await owned.close()
        for channel in (command, fallback):
            if channel is not None and channel.returncode is None:
                channel.kill()
                await channel.wait()
        if unrelated_channel is not None and unrelated_channel.returncode is None:
            unrelated_channel.kill()
            await unrelated_channel.wait()
        await master.close()
        # ContainerServer's outer context reaps all remaining remote processes.
        # Never interpret container PIDs as host PIDs, including on failure.
        shutil.rmtree(runtime_base)
