# SSH Wrapper

`ssh-wrapper` is a typed Python library for owning one native OpenSSH
ControlMaster and creating channels that can use only that master. It also
offers heartbeat supervision for one remote process group.

The runtime has no third-party Python dependency. It does not store
credentials, choose a host, reconnect a lost master, or define an application
protocol.

## Start here

- [Install the library](user/installation.md) on CPython 3.13 or 3.14.
- Follow the [typed usage guide](user/usage.md) to start and close a master.
- Review the [public API](user/api.md) before integrating lifecycle ownership.
- Understand the [security boundary](user/security.md) before using trusted SSH
  configuration or remote supervision.

Maintainers can begin with the [architecture](maintenance/architecture.md) and
[development workflow](maintenance/development.md). Normative guarantees live
only in the [contract catalog](contracts/README.md).

## Requirements

- CPython 3.13 or 3.14
- Linux as the supported runtime platform
- a native OpenSSH client
- `python3` on the remote host when using `OwnedRemoteProcess`

Importing the package, validating an authority, and constructing command
vectors do not need a live SSH endpoint or Linux session services. Linux is
still the declared and tested execution platform; session recovery and live
OpenSSH acceptance are Linux-specific.

The package is MIT licensed. Source, issues, and release history are available
in the [public repository](https://github.com/kogeler/ssh-wrapper).
