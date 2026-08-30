# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Run pytest with outbound Internet sockets disabled in this process."""

from __future__ import annotations

import argparse
import socket
from collections.abc import Sequence
from typing import Any


class NetworkBlockedError(OSError):
    """An Internet socket attempted to cross the unit-test boundary."""


class GuardedSocket(socket.socket):
    """Permit local sockets while rejecting IPv4 and IPv6 traffic."""

    def connect(self, address: Any) -> None:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise NetworkBlockedError("outbound network is disabled for tests")
        super().connect(address)

    def connect_ex(self, address: Any) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise NetworkBlockedError("outbound network is disabled for tests")
        return super().connect_ex(address)

    def sendto(self, data: Any, *arguments: Any) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise NetworkBlockedError("outbound network is disabled for tests")
        return super().sendto(data, *arguments)

    def sendmsg(self, buffers: Any, *arguments: Any) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise NetworkBlockedError("outbound network is disabled for tests")
        return super().sendmsg(buffers, *arguments)


def blocked_resolution(*_arguments: Any, **_options: Any) -> Any:
    """Reject DNS before a test can learn or contact an external address."""
    raise NetworkBlockedError("name resolution is disabled for tests")


def install_guard() -> None:
    """Install the process-local network guard before importing pytest."""
    socket.socket = GuardedSocket
    socket.create_connection = blocked_resolution
    socket.getaddrinfo = blocked_resolution


def probe() -> int:
    """Prove the guard rejects name resolution, streams, and datagrams."""

    def send_datagram(family: int, address: Any) -> None:
        with socket.socket(family, socket.SOCK_DGRAM) as datagram:
            datagram.sendto(b"probe", address)

    for operation in (
        lambda: socket.getaddrinfo("example.invalid", 443),
        lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
            ("192.0.2.1", 9)
        ),
        lambda: socket.socket(socket.AF_INET6, socket.SOCK_STREAM).connect(
            ("2001:db8::1", 9, 0, 0)
        ),
        lambda: send_datagram(socket.AF_INET, ("192.0.2.1", 9)),
        lambda: send_datagram(socket.AF_INET6, ("2001:db8::1", 9, 0, 0)),
    ):
        try:
            operation()
        except NetworkBlockedError:
            continue
        raise RuntimeError("network guard allowed an outbound operation")
    print("Network guard rejected DNS and direct IPv4/IPv6 stream/datagram traffic")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Install the guard and run either its probe or pytest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    arguments, pytest_arguments = parser.parse_known_args(argv)
    install_guard()
    if arguments.probe:
        if pytest_arguments:
            parser.error("--probe does not accept pytest arguments")
        return probe()
    import pytest

    return pytest.main(pytest_arguments)


if __name__ == "__main__":
    raise SystemExit(main())
