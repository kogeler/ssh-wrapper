# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Tests for validated SSH authority and one owned OpenSSH master."""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import signal
import sys
from pathlib import Path

import pytest

from ssh_wrapper import connection as connection_module
from ssh_wrapper.connection import (
    SSH_ISOLATION_OPTIONS,
    ConnectionMode,
    ConnectionSpec,
    ConnectionState,
    OpenSSHMaster,
    SSHMasterSettings,
    resolve_program,
    validate_ssh_alias,
    validate_ssh_host,
    validate_ssh_user,
)
from ssh_wrapper.errors import SSHError

FAKE_SSH = r"""#!{python}
import os
import signal
import socket
import sys
import time
from pathlib import Path

args = sys.argv[1:]

def value(flag):
    return args[args.index(flag) + 1]

socket_path = Path(value("-S"))
pid_path = Path(str(socket_path) + ".pid")
count_path = os.environ.get("FAKE_SSH_AUTH_COUNT")

if "-O" in args:
    operation = value("-O")
    if operation == "check":
        raise SystemExit(0 if socket_path.exists() else 255)
    if operation == "exit":
        try:
            os.kill(int(pid_path.read_text()), signal.SIGTERM)
        except (FileNotFoundError, ProcessLookupError):
            raise SystemExit(255)
        raise SystemExit(0)

if "-M" in args and "-N" in args:
    if count_path:
        count = Path(count_path)
        previous = int(count.read_text()) if count.exists() else 0
        count.write_text(str(previous + 1))
    if os.environ.get("FAKE_SSH_MASTER_ENV"):
        Path(os.environ["FAKE_SSH_MASTER_ENV"]).write_text(
            os.environ.get("RECOVERED_SESSION_VALUE", "missing")
        )
    if os.environ.get("FAKE_SSH_MASTER_STDERR"):
        sys.stderr.write(os.environ["FAKE_SSH_MASTER_STDERR"])
        sys.stderr.flush()
    if os.environ.get("FAKE_SSH_MASTER_STDERR_BYTES"):
        remaining = int(os.environ["FAKE_SSH_MASTER_STDERR_BYTES"])
        while remaining:
            chunk = b"x" * min(8192, remaining)
            os.write(sys.stderr.fileno(), chunk)
            remaining -= len(chunk)
        os.write(sys.stderr.fileno(), b"SSH_WRAPPER_STDERR_END")
    if os.environ.get("FAKE_SSH_FAIL_MASTER") == "1":
        raise SystemExit(23)
    server = None
    if os.environ.get("FAKE_SSH_NO_SOCKET") != "1":
        server = socket.socket(socket.AF_UNIX)
        server.bind(str(socket_path))
        server.listen()
        pid_path.write_text(str(os.getpid()))
    stopping = False
    def stop(_signum, _frame):
        global stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    while not stopping:
        time.sleep(0.02)
    if server is not None:
        server.close()
    socket_path.unlink(missing_ok=True)
    pid_path.unlink(missing_ok=True)
    raise SystemExit(0)

raise SystemExit(99)
"""


@pytest.fixture
def fake_ssh(tmp_path: Path) -> Path:
    path = tmp_path / "fake-ssh"
    path.write_text(FAKE_SSH.format(python=sys.executable), encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def settings(fake_ssh: Path) -> SSHMasterSettings:
    return SSHMasterSettings(
        ssh_path=fake_ssh,
        false_path=Path("/bin/false"),
        connect_timeout=0.5,
        server_alive_interval=7,
        server_alive_count_max=2,
        runtime_prefix="ssh-wrapper-test",
    )


@pytest.fixture(autouse=True)
def inherited_session_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    async def inherited() -> dict[str, str]:
        return os.environ.copy()

    monkeypatch.setattr(connection_module, "resolve_session_environment", inherited)


@pytest.mark.parametrize(
    "value", ("", "-host", "host name", "user@host", "host/path", "host$bad")
)
def test_alias_validation_rejects_ambiguous_tokens(value: str) -> None:
    with pytest.raises(SSHError, match="ssh_alias must"):
        validate_ssh_alias(value)


@pytest.mark.parametrize("value", ("-host", "host name", "user@host", "host/path"))
def test_host_validation_rejects_unsafe_tokens(value: str) -> None:
    with pytest.raises(SSHError, match="host must"):
        validate_ssh_host(value)


@pytest.mark.parametrize("value", ("-root", "user name", "user@host", "root/path"))
def test_user_validation_rejects_unsafe_tokens(value: str) -> None:
    with pytest.raises(SSHError, match="user must"):
        validate_ssh_user(value)


def test_connection_spec_keeps_authority_separate_from_transport() -> None:
    alias = ConnectionSpec.from_alias("configured-host")
    direct = ConnectionSpec.from_direct("2001:db8::7", "deploy", 2222)

    assert alias.mode is ConnectionMode.ALIAS
    assert alias.ssh_options == ()
    assert alias.rsync_target == "configured-host"
    assert alias.cache_key == "alias:configured-host"
    assert alias.display_target == "configured-host"
    assert direct.mode is ConnectionMode.DIRECT
    assert direct.destination == "2001:db8::7"
    assert direct.rsync_target == "[2001:db8::7]"
    assert direct.ssh_options == ("-l", "deploy", "-p", "2222")
    assert direct.cache_key == "direct:deploy@2001:db8::7:2222"
    assert direct.display_target == "deploy@[2001:db8::7]:2222"

    with pytest.raises(SSHError, match="port must"):
        ConnectionSpec.from_direct("host.example", "deploy", 0)

    for invalid in (
        {"mode": ConnectionMode.ALIAS},
        {
            "mode": ConnectionMode.ALIAS,
            "ssh_alias": "configured-host",
            "host": "host.example",
        },
        {
            "mode": ConnectionMode.DIRECT,
            "ssh_alias": "configured-host",
            "host": "host.example",
            "user": "deploy",
            "port": 22,
        },
        {"mode": ConnectionMode.DIRECT, "host": "host.example", "user": "deploy"},
        {"mode": "unsupported"},
    ):
        with pytest.raises(SSHError) as malformed:
            ConnectionSpec(**invalid)  # type: ignore[arg-type]
        assert malformed.value.code == "invalid_connection"


def test_program_resolution_returns_only_an_existing_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "ssh-test"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert resolve_program("ssh-test") == executable.resolve()
    with pytest.raises(SSHError) as raised:
        resolve_program("missing-program")
    assert raised.value.to_dict() == {
        "error": "missing_dependency",
        "message": "required command not found on PATH: missing-program",
        "details": {"command": "missing-program"},
    }


def test_uninitialized_master_rejects_secondary_channels(
    settings: SSHMasterSettings, tmp_path: Path
) -> None:
    master = OpenSSHMaster(
        settings,
        ConnectionSpec.from_alias("test-target"),
        runtime_base=tmp_path,
    )

    with pytest.raises(RuntimeError, match="not initialized"):
        master._master_argv()
    with pytest.raises(SSHError, match="no control socket"):
        master.mux_transport_argv()
    with pytest.raises(SSHError, match="runtime is unavailable"):
        master.create_mux_wrapper()

    master._create_runtime()
    try:
        with pytest.raises(ValueError, match="name is invalid"):
            master.create_mux_wrapper("../invalid")
    finally:
        assert master.runtime_dir is not None
        master.runtime_dir.rmdir()


def test_runtime_selection_uses_owned_xdg_and_rejects_unwritable_parent(
    settings: SSHMasterSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg))
    master = OpenSSHMaster(settings, ConnectionSpec.from_alias("test-target"))

    assert master._select_runtime_base() == xdg

    monkeypatch.setattr(connection_module.os, "access", lambda *_args: False)
    with pytest.raises(SSHError, match="no writable runtime directory"):
        master._select_runtime_base()


def test_control_path_falls_back_to_a_short_owned_runtime(
    settings: SSHMasterSettings, tmp_path: Path
) -> None:
    long_base = tmp_path / ("x" * 80)
    long_base.mkdir()
    master = OpenSSHMaster(
        settings,
        ConnectionSpec.from_alias("test-target"),
        runtime_base=long_base,
    )

    master._create_runtime()
    try:
        assert master.runtime_dir is not None
        assert master.control_path is not None
        assert master.runtime_dir.parent == Path(
            connection_module.tempfile.gettempdir()
        )
        assert master.control_path.name == "m"
        assert (
            len(os.fsencode(master.control_path))
            <= connection_module.MAX_CONTROL_PATH_BYTES
        )
    finally:
        assert master.runtime_dir is not None
        shutil.rmtree(master.runtime_dir)


@pytest.mark.asyncio
async def test_master_rejects_readiness_and_a_second_start(
    settings: SSHMasterSettings, tmp_path: Path
) -> None:
    master = OpenSSHMaster(
        settings,
        ConnectionSpec.from_alias("test-target"),
        runtime_base=tmp_path,
    )
    with pytest.raises(SSHError, match="not ready"):
        await master.ensure_ready()

    await master.start()
    try:
        with pytest.raises(SSHError, match="only be started once"):
            await master.start()
    finally:
        await master.close()


@pytest.mark.asyncio
async def test_master_authenticates_once_and_reuses_private_mux(
    settings: SSHMasterSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    count = tmp_path / "auth-count"
    monkeypatch.setenv("FAKE_SSH_AUTH_COUNT", str(count))
    master = OpenSSHMaster(
        settings,
        ConnectionSpec.from_alias("test-target"),
        runtime_base=tmp_path,
    )

    await master.start()
    await master.ensure_ready()
    await master.ensure_ready()
    stderr_task = master._stderr_task

    assert master.state is ConnectionState.READY
    assert count.read_text(encoding="utf-8") == "1"
    assert stderr_task is not None and not stderr_task.done()
    assert master.runtime_dir is not None
    assert master.runtime_dir.stat().st_mode & 0o777 == 0o700
    assert master.control_path is not None and master.control_path.is_socket()
    transport = master.mux_transport_argv()
    assert "test-target" not in transport
    for barrier in (
        "BatchMode=yes",
        "NumberOfPasswordPrompts=0",
        "PubkeyAuthentication=no",
        f"ProxyCommand={settings.false_path}",
        *SSH_ISOLATION_OPTIONS,
    ):
        assert barrier in transport

    await master.close()
    await master.close()
    assert master.state is ConnectionState.CLOSED
    assert stderr_task.done()
    assert master._stderr_task is None
    assert master._stderr_tail.data == b""
    assert master.runtime_dir is not None and not master.runtime_dir.exists()


@pytest.mark.asyncio
async def test_lost_master_never_reauthenticates(
    settings: SSHMasterSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    count = tmp_path / "auth-count"
    monkeypatch.setenv("FAKE_SSH_AUTH_COUNT", str(count))
    master = OpenSSHMaster(
        settings,
        ConnectionSpec.from_alias("test-target"),
        runtime_base=tmp_path,
    )
    await master.start()
    assert master.process is not None

    os.killpg(master.process.pid, signal.SIGTERM)
    await master.process.wait()
    with pytest.raises(SSHError) as raised:
        await master.ensure_ready()

    assert raised.value.code == "connection_lost"
    assert count.read_text(encoding="utf-8") == "1"
    await master.close()
    assert count.read_text(encoding="utf-8") == "1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("diagnostic", "message"),
    (
        (
            "read_passphrase: can't open /dev/tty: no device\nDISPLAY not set\n",
            connection_module.INTERACTIVE_AUTHENTICATION_ERROR,
        ),
        ("proxy failed through /private/path\n", "SSH master exited with status 23"),
    ),
)
async def test_start_failure_is_bounded_path_free_and_cleans_runtime(
    diagnostic: str,
    message: str,
    settings: SSHMasterSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SSH_MASTER_STDERR", diagnostic)
    monkeypatch.setenv("FAKE_SSH_FAIL_MASTER", "1")
    master = OpenSSHMaster(
        settings,
        ConnectionSpec.from_alias("test-target"),
        runtime_base=tmp_path,
    )

    with pytest.raises(SSHError) as raised:
        await master.start()

    assert raised.value.code == "connection_start_failed"
    assert raised.value.message == message
    assert diagnostic not in raised.value.message
    assert "/private/path" not in raised.value.message
    assert master.state is ConnectionState.CLOSED
    assert master._stderr_task is None
    assert master._stderr_tail.data == b""
    assert master.runtime_dir is not None and not master.runtime_dir.exists()


@pytest.mark.asyncio
async def test_recovered_environment_is_used_only_for_initial_master(
    settings: SSHMasterSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = tmp_path / "master-environment"
    monkeypatch.setenv("FAKE_SSH_MASTER_ENV", str(record))
    calls = 0

    async def recovered() -> dict[str, str]:
        nonlocal calls
        calls += 1
        environment = os.environ.copy()
        environment["RECOVERED_SESSION_VALUE"] = "recovered"
        return environment

    monkeypatch.setattr(connection_module, "resolve_session_environment", recovered)
    real_create = asyncio.create_subprocess_exec
    environments: list[dict[str, str] | None] = []

    async def recording_create(
        *args: str, **kwargs: object
    ) -> asyncio.subprocess.Process:
        supplied = kwargs.get("env")
        assert supplied is None or isinstance(supplied, dict)
        environments.append(supplied)
        return await real_create(*args, **kwargs)

    monkeypatch.setattr(
        connection_module.asyncio, "create_subprocess_exec", recording_create
    )
    master = OpenSSHMaster(
        settings,
        ConnectionSpec.from_alias("test-target"),
        runtime_base=tmp_path,
    )

    await master.start()
    await master.ensure_ready()
    await master.close()

    assert calls == 1
    assert record.read_text(encoding="utf-8") == "recovered"
    assert environments[0] is not None
    assert environments[0]["RECOVERED_SESSION_VALUE"] == "recovered"
    assert all(environment is None for environment in environments[1:])


@pytest.mark.asyncio
async def test_ready_master_continuously_drains_bounded_stderr(
    settings: SSHMasterSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_SSH_MASTER_STDERR_BYTES", str(512 * 1024))
    master = OpenSSHMaster(
        settings,
        ConnectionSpec.from_alias("test-target"),
        runtime_base=tmp_path,
    )

    await master.start()

    assert len(master._stderr_tail.data) <= connection_module.MASTER_STDERR_TAIL_BYTES
    assert master._stderr_tail.data.endswith(b"SSH_WRAPPER_STDERR_END")
    await master.close()


def test_direct_transport_and_private_wrapper_never_embed_destination(
    settings: SSHMasterSettings, tmp_path: Path
) -> None:
    connection = ConnectionSpec.from_direct("host.example", "deploy", 2222)
    master = OpenSSHMaster(settings, connection, runtime_base=tmp_path)
    master._create_runtime()
    try:
        assert master._master_argv()[-6:] == [
            "-l",
            "deploy",
            "-p",
            "2222",
            "--",
            "host.example",
        ]
        assert master.command_argv("true")[-7:] == [
            "-l",
            "deploy",
            "-p",
            "2222",
            "--",
            "host.example",
            "true",
        ]
        transport = shlex.split(master.rsync_ssh_command())
        assert transport[-4:] == ["-l", "deploy", "-p", "2222"]
        assert "host.example" not in transport

        wrapper = master.create_mux_wrapper("consumer-ssh")
        content = wrapper.read_text(encoding="utf-8")
        assert wrapper.stat().st_mode & 0o777 == 0o700
        assert content.startswith("#!/bin/sh\nset -eu\nexec ")
        assert ' "$@"\n' in content
        assert "eval" not in content
        assert "host.example" not in content
    finally:
        assert master.runtime_dir is not None
        for path in master.runtime_dir.iterdir():
            path.unlink()
        master.runtime_dir.rmdir()
