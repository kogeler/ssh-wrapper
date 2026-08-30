# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Hermetic acceptance against one unprivileged loopback OpenSSH server."""

from __future__ import annotations

import asyncio
import getpass
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
from contextlib import suppress
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
from ssh_wrapper.connection import MASTER_STDERR_TAIL_BYTES

pytestmark = [
    pytest.mark.acceptance,
    pytest.mark.skipif(
        sys.platform != "linux", reason="OpenSSH acceptance is Linux-only"
    ),
]


def _program(name: str) -> Path:
    resolved = shutil.which(name)
    if resolved is None:
        pytest.skip(f"required OpenSSH acceptance command is unavailable: {name}")
    return Path(resolved).resolve(strict=True)


def _unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def _wait_for_text(path: Path, needle: str, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        with suppress(OSError):
            if needle in path.read_text(encoding="utf-8"):
                return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {needle!r}")


async def _wait_for_file(path: Path, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if path.is_file() and path.stat().st_size:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {path.name}")


async def _wait_for_pid_exit(pid: int, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"owned process {pid} did not exit")


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

    ssh = _program("ssh")
    sshd = _program("sshd")
    keygen = _program("ssh-keygen")
    false = _program("false")
    username = getpass.getuser()
    monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
    monkeypatch.delenv("SSH_AGENT_PID", raising=False)
    port = _unused_loopback_port()
    host_key = tmp_path / "host-ed25519"
    client_key = tmp_path / "client-ed25519"
    authorized_keys = tmp_path / "authorized_keys"
    known_hosts = tmp_path / "known_hosts"
    server_config = tmp_path / "sshd_config"
    client_config = tmp_path / "ssh_config"
    server_log = tmp_path / "sshd.log"
    server_pid_file = tmp_path / "sshd.pid"
    wrapper = tmp_path / "isolated-ssh"

    _generate_key(keygen, host_key)
    _generate_key(keygen, client_key)
    key_type, key_data, *_rest = (
        (client_key.with_suffix(".pub")).read_text(encoding="ascii").split()
    )
    authorized_keys.write_text(
        f"restrict {key_type} {key_data} ssh-wrapper-acceptance\n",
        encoding="ascii",
    )
    authorized_keys.chmod(0o600)
    host_type, host_data, *_rest = (
        (host_key.with_suffix(".pub")).read_text(encoding="ascii").split()
    )
    known_hosts.write_text(
        f"[127.0.0.1]:{port} {host_type} {host_data}\n", encoding="ascii"
    )
    known_hosts.chmod(0o600)

    server_config.write_text(
        "\n".join(
            (
                f"Port {port}",
                "ListenAddress 127.0.0.1",
                f"HostKey {host_key}",
                f"PidFile {server_pid_file}",
                f"AuthorizedKeysFile {authorized_keys}",
                "StrictModes no",
                "UsePAM no",
                "AuthenticationMethods publickey",
                "PubkeyAuthentication yes",
                "PasswordAuthentication no",
                "KbdInteractiveAuthentication no",
                "HostbasedAuthentication no",
                "PermitEmptyPasswords no",
                "PermitRootLogin no",
                f"AllowUsers {username}",
                "DisableForwarding yes",
                "PermitUserEnvironment no",
                "LogLevel VERBOSE",
                "Subsystem sftp internal-sftp",
                "",
            )
        ),
        encoding="utf-8",
    )
    client_config.write_text(
        "\n".join(
            (
                "Host *",
                f"  IdentityFile {client_key}",
                "  IdentitiesOnly yes",
                "  IdentityAgent none",
                "  AddKeysToAgent no",
                f"  UserKnownHostsFile {known_hosts}",
                "  GlobalKnownHostsFile /dev/null",
                "  StrictHostKeyChecking yes",
                "  UpdateHostKeys no",
                "  CheckHostIP no",
                "  PasswordAuthentication no",
                "  KbdInteractiveAuthentication no",
                "  HostbasedAuthentication no",
                "  GSSAPIAuthentication no",
                "  ProxyCommand none",
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

    log_stream = server_log.open("wb")
    server = await asyncio.create_subprocess_exec(
        str(sshd),
        "-D",
        "-e",
        "-f",
        str(server_config),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=log_stream,
        start_new_session=True,
    )
    master = OpenSSHMaster(
        SSHMasterSettings(
            ssh_path=wrapper,
            false_path=false,
            connect_timeout=8,
            server_alive_interval=2,
            server_alive_count_max=2,
            runtime_prefix="ssh-wrapper-acceptance",
        ),
        ConnectionSpec.from_direct("127.0.0.1", username, port),
        runtime_base=tmp_path,
    )
    unrelated_channel: asyncio.subprocess.Process | None = None
    unrelated_pid: int | None = None
    try:
        await _wait_for_text(server_log, "Server listening")
        assert "SSH_AUTH_SOCK" not in os.environ
        assert "IdentityAgent none" in client_config.read_text(encoding="utf-8")

        await master.start()
        assert master.state is ConnectionState.READY
        assert master.process is not None
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

        unrelated_pid_file = tmp_path / "unrelated.pid"
        unrelated_program = shlex.join(
            (
                str(Path(sys.executable).resolve()),
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
        await _wait_for_file(unrelated_pid_file)
        unrelated_pid = int(unrelated_pid_file.read_text(encoding="ascii"))

        owned_pid_file = tmp_path / "owned.pid"
        owned = OwnedRemoteProcess(
            master,
            (
                str(Path(sys.executable).resolve()),
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
        await _wait_for_file(owned_pid_file)
        owned_pid = int(owned_pid_file.read_text(encoding="ascii"))
        assert os.getpgid(owned_pid) == owned_pid
        await owned.close()
        await _wait_for_pid_exit(owned_pid)
        os.kill(unrelated_pid, 0)
        assert len(owned.stdout_tail.data) <= 512
        assert len(owned.stderr_tail.data) <= 512

        os.kill(unrelated_pid, signal.SIGTERM)
        await _wait_for_pid_exit(unrelated_pid)
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
        log = server_log.read_text(encoding="utf-8")
        assert (
            sum(line.startswith("Connection from ") for line in log.splitlines()) == 1
        )
        assert sum("Accepted publickey for " in line for line in log.splitlines()) == 1
    finally:
        if unrelated_channel is not None and unrelated_channel.returncode is None:
            unrelated_channel.kill()
            await unrelated_channel.wait()
        if unrelated_pid is not None:
            with suppress(ProcessLookupError):
                os.kill(unrelated_pid, signal.SIGKILL)
        await master.close()
        if server.returncode is None:
            with suppress(ProcessLookupError):
                os.killpg(server.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(server.wait(), timeout=5)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    os.killpg(server.pid, signal.SIGKILL)
                await server.wait()
        log_stream.close()
