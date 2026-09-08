# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Validated authority and one owned native OpenSSH multiplexing master."""

from __future__ import annotations

import asyncio
import ipaddress
import math
import os
import re
import shlex
import shutil
import stat
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ._process import complete_task, finish_tasks, spawn_owned, stop_group, wait_exit
from .bounded import BoundedTail
from .errors import SSHError
from .session_environment import resolve_session_environment

CONTROL_CHECK_TIMEOUT = 5.0
PROCESS_STOP_TIMEOUT = 5.0
# Linux sun_path allows 107 bytes plus NUL; OpenSSH appends '.' and 16 random
# characters while atomically binding its temporary mux listener.
MAX_CONTROL_PATH_BYTES = 90
MASTER_STDERR_TAIL_BYTES = 16 * 1024
MASTER_STDERR_READ_BYTES = 4096
MASTER_STDERR_DRAIN_TIMEOUT = 1.0

INTERACTIVE_AUTHENTICATION_ERROR = (
    "SSH authentication requires an interactive system prompt, but no usable "
    "user session environment was available"
)
INTERACTIVE_AUTHENTICATION_MARKERS = (
    "can't open /dev/tty",
    "cannot open /dev/tty",
    "display not set",
    "no askpass program specified",
    "ssh_askpass not set",
    "ssh_askpass:",
    "cannot notify: no askpass",
    "requested to askpass",
)
INTERACTIVE_AUTHENTICATION_MARKER_PAIRS = (
    ("sign_and_send_pubkey: signing failed", "agent refused operation"),
    ("sign_and_send_pubkey: signing failed", "incorrect passphrase supplied"),
    ("load key", "incorrect passphrase supplied"),
)

SSH_ALIAS_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,254}\Z")
SSH_HOST_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,252}\Z")
SSH_USER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}\Z")

SSH_ISOLATION_OPTIONS = (
    "ClearAllForwardings=yes",
    "Tunnel=no",
    "ForwardAgent=no",
    "ForwardX11=no",
    "ForwardX11Trusted=no",
    "PermitLocalCommand=no",
    "RemoteCommand=none",
    "ForkAfterAuthentication=no",
)


def validate_ssh_alias(value: str) -> str:
    """Validate one trusted OpenSSH alias token."""
    if not isinstance(value, str) or not SSH_ALIAS_PATTERN.fullmatch(value):
        raise SSHError(
            "invalid_connection",
            "ssh_alias must use only letters, digits, '.', '_', and '-' and cannot start with '-'",
        )
    return value


def validate_ssh_host(value: str) -> str:
    """Validate one direct IP address or conservative DNS name."""
    if not isinstance(value, str) or (
        "%" in value and not re.fullmatch(r"[A-Za-z0-9_.-]+", value.partition("%")[2])
    ):
        raise SSHError("invalid_connection", "host must be a valid host or IP address")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        if not SSH_HOST_PATTERN.fullmatch(value):
            raise SSHError(
                "invalid_connection",
                "host must be an IPv4 address, an unbracketed IPv6 address, or a conservative DNS name",
            ) from None
    return value


def validate_ssh_user(value: str) -> str:
    """Validate one direct remote user token."""
    if not isinstance(value, str) or not SSH_USER_PATTERN.fullmatch(value):
        raise SSHError(
            "invalid_connection",
            "user must use only letters, digits, '.', '_', '+', and '-' and cannot start with '-'",
        )
    return value


def resolve_program(name: str) -> Path:
    """Resolve an executable without accepting a caller-controlled path."""
    resolved = shutil.which(name)
    if resolved is None:
        raise SSHError(
            "missing_dependency",
            f"required command not found on PATH: {name}",
            {"command": name},
        )
    return Path(resolved).resolve(strict=True)


class ConnectionMode(StrEnum):
    """Supported authority selection forms."""

    ALIAS = "alias"
    DIRECT = "direct"


@dataclass(frozen=True, slots=True)
class ConnectionSpec:
    """Validated OpenSSH authority kept separate from process arguments."""

    mode: ConnectionMode
    ssh_alias: str | None = None
    host: str | None = None
    user: str | None = None
    port: int | None = None

    def __post_init__(self) -> None:
        """Reject incomplete or mixed authority state from direct construction."""
        if self.mode is ConnectionMode.ALIAS:
            if (
                self.ssh_alias is None
                or self.host is not None
                or self.user is not None
                or self.port is not None
            ):
                raise SSHError(
                    "invalid_connection",
                    "alias connection must contain only ssh_alias",
                )
            validate_ssh_alias(self.ssh_alias)
            return
        if self.mode is ConnectionMode.DIRECT:
            if self.ssh_alias is not None or self.host is None or self.user is None:
                raise SSHError(
                    "invalid_connection",
                    "direct connection requires host, user, and port",
                )
            if type(self.port) is not int or not 1 <= self.port <= 65_535:
                raise SSHError("invalid_connection", "port must be between 1 and 65535")
            validate_ssh_host(self.host)
            validate_ssh_user(self.user)
            return
        raise SSHError("invalid_connection", "connection mode is invalid")

    @classmethod
    def from_alias(cls, ssh_alias: str) -> ConnectionSpec:
        """Build an alias authority."""
        return cls(mode=ConnectionMode.ALIAS, ssh_alias=ssh_alias)

    @classmethod
    def from_direct(cls, host: str, user: str, port: int = 22) -> ConnectionSpec:
        """Build a direct host, user, and port authority."""
        return cls(
            mode=ConnectionMode.DIRECT,
            host=host,
            user=user,
            port=port,
        )

    @property
    def destination(self) -> str:
        """Return the destination token passed after the option terminator."""
        if self.mode is ConnectionMode.ALIAS:
            if self.ssh_alias is None:
                raise RuntimeError("validated alias connection is incomplete")
            return self.ssh_alias
        if self.host is None:
            raise RuntimeError("validated direct connection is incomplete")
        return self.host

    @property
    def ssh_options(self) -> tuple[str, ...]:
        """Return direct authority options or none for a trusted alias."""
        if self.mode is ConnectionMode.ALIAS:
            return ()
        if self.user is None or self.port is None:
            raise RuntimeError("validated direct connection is incomplete")
        return ("-l", self.user, "-p", str(self.port))

    @property
    def rsync_target(self) -> str:
        """Return an rsync-safe destination host token."""
        destination = self.destination
        if self.mode is ConnectionMode.DIRECT and ":" in destination:
            return f"[{destination}]"
        return destination

    @property
    def cache_key(self) -> str:
        """Return a stable non-secret authority identity."""
        if self.mode is ConnectionMode.ALIAS:
            return f"alias:{self.destination}"
        if self.user is None or self.port is None:
            raise RuntimeError("validated direct connection is incomplete")
        return f"direct:{self.user}@{self.destination}:{self.port}"

    @property
    def display_target(self) -> str:
        """Return a human-readable sanitized authority."""
        if self.mode is ConnectionMode.ALIAS:
            return self.destination
        if self.user is None or self.port is None:
            raise RuntimeError("validated direct connection is incomplete")
        host = f"[{self.destination}]" if ":" in self.destination else self.destination
        return f"{self.user}@{host}:{self.port}"


@dataclass(frozen=True, slots=True)
class SSHMasterSettings:
    """Only the immutable settings needed by an OpenSSH master."""

    ssh_path: Path
    false_path: Path
    connect_timeout: float
    server_alive_interval: int = 15
    server_alive_count_max: int = 3
    runtime_prefix: str = "remote-ssh"

    def __post_init__(self) -> None:
        if not math.isfinite(self.connect_timeout) or self.connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive and finite")
        if any(
            type(value) is not int or value < 0
            for value in (self.server_alive_interval, self.server_alive_count_max)
        ):
            raise ValueError("server keepalive settings must be nonnegative integers")
        if not self.runtime_prefix or any(
            character in self.runtime_prefix for character in ("/", "\\", "\x00")
        ):
            raise ValueError("runtime_prefix must be a non-empty filename prefix")


class ConnectionState(StrEnum):
    """Lifecycle states for one owned master."""

    NEW = "new"
    STARTING = "starting"
    READY = "ready"
    LOST = "lost"
    CLOSING = "closing"
    CLOSED = "closed"


class OpenSSHMaster:
    """Own exactly one OpenSSH master process and its private mux socket."""

    def __init__(
        self,
        settings: SSHMasterSettings,
        connection: ConnectionSpec,
        *,
        runtime_base: Path | None = None,
    ) -> None:
        self.settings = settings
        self.connection = connection
        self._runtime_base = runtime_base
        self.runtime_dir: Path | None = None
        self.control_path: Path | None = None
        self.process: asyncio.subprocess.Process | None = None
        self.state = ConnectionState.NEW
        self._stderr_tail = BoundedTail(MASTER_STDERR_TAIL_BYTES)
        self._stderr_task: asyncio.Task[None] | None = None
        self._start_task: asyncio.Task[None] | None = None
        self._close_task: asyncio.Task[None] | None = None

    def _select_runtime_base(self) -> Path:
        if self._runtime_base is not None:
            base = self._runtime_base.resolve(strict=True)
        else:
            configured = os.environ.get("XDG_RUNTIME_DIR")
            if configured:
                candidate = Path(configured)
                try:
                    if not candidate.is_absolute():
                        raise OSError("XDG_RUNTIME_DIR is not absolute")
                    base = candidate.resolve(strict=True)
                    if not base.is_dir() or base.stat().st_uid != os.getuid():
                        raise OSError("XDG_RUNTIME_DIR is not an owned directory")
                except (OSError, RuntimeError):
                    base = Path(tempfile.gettempdir()).resolve(strict=True)
            else:
                base = Path(tempfile.gettempdir()).resolve(strict=True)
        if not base.is_dir() or not os.access(base, os.W_OK | os.X_OK):
            raise SSHError(
                "connection_start_failed", "no writable runtime directory is available"
            )
        return base

    def _create_runtime(self) -> None:
        base = self._select_runtime_base()
        prefix = f"{self.settings.runtime_prefix}-{os.getuid()}-"
        runtime = Path(tempfile.mkdtemp(prefix=prefix, dir=base))
        self.runtime_dir = runtime
        os.chmod(runtime, 0o700)
        control = runtime / "mux.sock"

        if len(os.fsencode(control)) > MAX_CONTROL_PATH_BYTES or "${" in str(control):
            shutil.rmtree(runtime)
            fallback = Path(tempfile.gettempdir()).resolve(strict=True)
            runtime = Path(tempfile.mkdtemp(prefix=f"sw-{os.getuid()}-", dir=fallback))
            self.runtime_dir = runtime
            os.chmod(runtime, 0o700)
            control = runtime / "m"
        if len(os.fsencode(control)) > MAX_CONTROL_PATH_BYTES or "${" in str(control):
            shutil.rmtree(runtime)
            raise SSHError(
                "connection_start_failed",
                "cannot create a short enough SSH control path",
            )

        self.runtime_dir = runtime
        self.control_path = control

    def _master_argv(self) -> list[str]:
        if self.control_path is None:
            raise RuntimeError("runtime directory is not initialized")
        return [
            str(self.settings.ssh_path),
            "-M",
            "-N",
            "-S",
            str(self.control_path).replace("%", "%%"),
            "-o",
            "ControlMaster=yes",
            "-o",
            "ControlPersist=no",
            *(item for option in SSH_ISOLATION_OPTIONS for item in ("-o", option)),
            "-o",
            f"ConnectTimeout={max(1, int(self.settings.connect_timeout))}",
            "-o",
            f"ServerAliveInterval={self.settings.server_alive_interval}",
            "-o",
            f"ServerAliveCountMax={self.settings.server_alive_count_max}",
            *self.connection.ssh_options,
            "--",
            self.connection.destination,
        ]

    def mux_transport_argv(self) -> list[str]:
        """Return fixed ssh options without a destination or remote command."""
        if self.control_path is None:
            raise SSHError("connection_lost", "SSH master has no control socket")
        return [
            str(self.settings.ssh_path),
            "-T",
            "-S",
            str(self.control_path).replace("%", "%%"),
            "-o",
            "ControlMaster=no",
            "-o",
            "ControlPersist=no",
            "-o",
            "BatchMode=yes",
            "-o",
            "NumberOfPasswordPrompts=0",
            *(item for option in SSH_ISOLATION_OPTIONS for item in ("-o", option)),
            "-o",
            f"ProxyCommand={shlex.quote(str(self.settings.false_path)).replace('%', '%%')}",
            "-o",
            "StdinNull=no",
            "-o",
            "PubkeyAuthentication=no",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            "KbdInteractiveAuthentication=no",
            "-o",
            "GSSAPIAuthentication=no",
            "-o",
            "HostbasedAuthentication=no",
            *self.connection.ssh_options,
        ]

    def command_argv(self, remote_program: str) -> list[str]:
        """Append the exact destination and one fixed remote program."""
        transport = self.mux_transport_argv()
        return [
            transport[0],
            "-o",
            "SessionType=default",
            *transport[1:],
            "--",
            self.connection.destination,
            remote_program,
        ]

    def mux_ssh_command(self) -> str:
        """Return a shell-escaped command for mux-aware SSH consumers."""
        return shlex.join(self.mux_transport_argv())

    def create_mux_wrapper(self, name: str = "mux-ssh") -> Path:
        """Create a private executable that appends only consumer arguments."""
        runtime = self.runtime_dir
        if runtime is None or self.control_path is None:
            raise SSHError("connection_lost", "SSH master runtime is unavailable")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", name):
            raise ValueError("wrapper name is invalid")
        path = runtime / name
        content = (
            f'#!/bin/sh\nset -eu\nexec {shlex.join(self.mux_transport_argv())} "$@"\n'
        ).encode()
        try:
            descriptor = os.open(
                path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_CLOEXEC,
                0o700,
            )
            with os.fdopen(descriptor, "wb") as destination:
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())
        except OSError as error:
            raise SSHError(
                "connection_start_failed", "cannot create the private SSH wrapper"
            ) from error
        return path

    def rsync_ssh_command(self) -> str:
        """Return the no-fallback SSH command accepted by rsync ``-e``."""
        return self.mux_ssh_command()

    async def _control_operation(self, operation: str) -> tuple[int, bytes, bytes]:
        if self.control_path is None:
            return 255, b"", b"control socket is not initialized"
        process = await spawn_owned(
            *self.mux_transport_argv(),
            "-O",
            operation,
            "--",
            self.connection.destination,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_tail = BoundedTail(MASTER_STDERR_TAIL_BYTES)
        stderr_tail = BoundedTail(MASTER_STDERR_TAIL_BYTES)

        async def drain(stream: asyncio.StreamReader, tail: BoundedTail) -> None:
            while chunk := await stream.read(MASTER_STDERR_READ_BYTES):
                tail.append(chunk)

        drains = tuple(
            asyncio.create_task(drain(stream, tail))
            for stream, tail in (
                (process.stdout, stdout_tail),
                (process.stderr, stderr_tail),
            )
            if stream is not None
        )

        async def cleanup() -> None:
            try:
                await stop_group(process, MASTER_STDERR_DRAIN_TIMEOUT)
            finally:
                await finish_tasks(drains, MASTER_STDERR_DRAIN_TIMEOUT)

        try:
            async with asyncio.timeout(CONTROL_CHECK_TIMEOUT):
                await wait_exit(process)
                await asyncio.gather(*drains)
            return process.returncode or 0, stdout_tail.data, stderr_tail.data
        except TimeoutError:
            return 255, b"", b"control operation timed out"
        finally:
            await complete_task(asyncio.create_task(cleanup()))

    def _socket_exists(self) -> bool:
        if self.control_path is None:
            return False
        try:
            return stat.S_ISSOCK(self.control_path.stat().st_mode)
        except OSError:
            return False

    async def _drain_master_stderr(self, stream: asyncio.StreamReader) -> None:
        while chunk := await stream.read(MASTER_STDERR_READ_BYTES):
            self._stderr_tail.append(chunk)

    async def _finish_stderr_drain(self, *, clear: bool) -> None:
        task = self._stderr_task

        async def finish() -> None:
            try:
                if task is not None:
                    _done, pending = await asyncio.wait(
                        (task,), timeout=MASTER_STDERR_DRAIN_TIMEOUT
                    )
                    if pending and self.process is not None:
                        await stop_group(self.process, MASTER_STDERR_DRAIN_TIMEOUT)
                    await finish_tasks((task,), MASTER_STDERR_DRAIN_TIMEOUT)
            finally:
                self._stderr_task = None
                if clear:
                    self._stderr_tail.clear()

        await complete_task(asyncio.create_task(finish()))

    def _master_exit_error(self) -> SSHError:
        diagnostic = self._stderr_tail.text().casefold()
        if any(
            marker in diagnostic for marker in INTERACTIVE_AUTHENTICATION_MARKERS
        ) or any(
            first in diagnostic and second in diagnostic
            for first, second in INTERACTIVE_AUTHENTICATION_MARKER_PAIRS
        ):
            return SSHError("connection_start_failed", INTERACTIVE_AUTHENTICATION_ERROR)
        if self.process is None or self.process.returncode is None:
            raise RuntimeError("SSH master exit status is unavailable")
        return SSHError(
            "connection_start_failed",
            f"SSH master exited with status {self.process.returncode}",
        )

    async def start(self) -> None:
        """Authenticate once and wait until the owned master is ready."""
        if self.state is not ConnectionState.NEW:
            raise SSHError(
                "connection_start_failed", "SSH master can only be started once"
            )
        self.state = ConnectionState.STARTING
        self._start_task = asyncio.create_task(self._start())
        try:
            await asyncio.shield(self._start_task)
        except OSError:
            await self.close()
            raise SSHError(
                "connection_start_failed", "cannot start the SSH master"
            ) from None
        except BaseException:
            await self.close()
            raise

    async def _start(self) -> None:
        self._create_runtime()
        environment = await resolve_session_environment()
        self.process = await spawn_owned(
            *self._master_argv(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        if self.process.stderr is None:
            raise SSHError(
                "connection_start_failed",
                "cannot capture SSH master diagnostics",
            )
        self._stderr_task = asyncio.create_task(
            self._drain_master_stderr(self.process.stderr)
        )
        try:
            async with asyncio.timeout(self.settings.connect_timeout):
                await self._wait_ready()
        except TimeoutError:
            raise SSHError(
                "connection_start_failed",
                "SSH master did not become ready before the startup deadline",
            ) from None

    async def _wait_ready(self) -> None:
        if self.process is None:
            raise RuntimeError("SSH master process is not initialized")
        while True:
            if self.process.returncode is not None:
                await self._finish_stderr_drain(clear=False)
                raise self._master_exit_error()
            if self._socket_exists():
                returncode, _stdout, _stderr = await self._control_operation("check")
                if returncode == 0:
                    self.state = ConnectionState.READY
                    return
            await asyncio.sleep(0.1)

    async def ensure_ready(self) -> None:
        """Check the process, socket, and control operation without reconnecting."""
        if self.state is not ConnectionState.READY:
            raise SSHError(
                "connection_lost", f"SSH master is not ready (state: {self.state})"
            )
        if (
            self.process is None
            or self.process.returncode is not None
            or not self._socket_exists()
        ):
            self.state = ConnectionState.LOST
            raise SSHError("connection_lost", "SSH master process or socket is gone")
        try:
            returncode, _stdout, _stderr = await self._control_operation("check")
        except OSError:
            returncode = 255
        if self.state is not ConnectionState.READY:
            raise SSHError(
                "connection_lost", "SSH master was closed during the control check"
            )
        if returncode != 0:
            self.state = ConnectionState.LOST
            raise SSHError(
                "connection_lost",
                "SSH master control check failed",
            )

    async def _stop_process(self) -> None:
        if self.process is None or self.process.returncode is not None:
            return
        await stop_group(self.process, PROCESS_STOP_TIMEOUT)

    async def close(self) -> None:
        """Close the owned master and remove only its private runtime state."""
        if self._close_task is None:
            self.state = ConnectionState.CLOSING
            self._close_task = asyncio.create_task(self._close())
        await complete_task(self._close_task)

    async def _close(self) -> None:
        startup = self._start_task
        if startup is not None and not startup.done():
            startup.cancel()
            await asyncio.gather(startup, return_exceptions=True)
        try:
            if (
                self.process is not None
                and self.process.returncode is None
                and self._socket_exists()
            ):
                try:
                    await self._control_operation("exit")
                except OSError:
                    pass
                try:
                    await asyncio.wait_for(
                        wait_exit(self.process), timeout=PROCESS_STOP_TIMEOUT
                    )
                except TimeoutError:
                    await self._stop_process()
            else:
                await self._stop_process()
        finally:
            try:
                await self._stop_process()
            finally:
                try:
                    await self._finish_stderr_drain(clear=True)
                finally:
                    runtime = self.runtime_dir
                    if runtime is not None:
                        try:
                            if runtime.stat().st_uid == os.getuid():
                                shutil.rmtree(runtime)
                        except FileNotFoundError:
                            pass
                    self.state = ConnectionState.CLOSED
