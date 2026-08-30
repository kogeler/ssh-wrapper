# SSH Wrapper

`ssh-wrapper` owns one native OpenSSH ControlMaster and exposes only
no-fallback mux channels. It can also supervise one remote process group with
a bounded heartbeat lease, so owner loss cleans up only that group.

The runtime is fully typed and uses only the Python standard library. It does
not choose hosts, store credentials, reconnect a lost master, or define a
consumer protocol.

## Requirements

- CPython 3.13 or 3.14
- Linux
- an OpenSSH client
- `python3` on the remote host only when using `OwnedRemoteProcess`

## Installation

Install an exact reviewed version with pip:

```bash
python3.13 -m pip install "ssh-wrapper==0.1.0"
```

Use `python3.14` in the same command when that is the selected supported
interpreter.

This is a library and does not install a command-line entry point, so `pipx`
is not an appropriate installation method.

## Basic use

```python
import asyncio
from pathlib import Path

from ssh_wrapper import ConnectionSpec, OpenSSHMaster, SSHMasterSettings


async def run() -> bytes:
    master = OpenSSHMaster(
        SSHMasterSettings(
            ssh_path=Path("/usr/bin/ssh"),
            false_path=Path("/usr/bin/false"),
            connect_timeout=30,
        ),
        ConnectionSpec.from_alias("workstation"),
    )
    await master.start()
    try:
        process = await asyncio.create_subprocess_exec(
            *master.command_argv("uname -a"),
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await process.communicate()
        if process.returncode:
            raise RuntimeError(f"remote command exited {process.returncode}")
        return stdout
    finally:
        await master.close()
```

The caller owns each ordinary secondary process and its output. Use
`OwnedRemoteProcess` for a long-lived child that must remain tied to an owner
lease.

## Project links

- [Documentation](https://kogeler.github.io/ssh-wrapper/)
- [Repository](https://github.com/kogeler/ssh-wrapper)
- [Issue tracker](https://github.com/kogeler/ssh-wrapper/issues)
- [Changelog](https://github.com/kogeler/ssh-wrapper/blob/main/CHANGELOG.md)
- [Contributing](https://github.com/kogeler/ssh-wrapper/blob/main/CONTRIBUTING.md)
- [Security policy](https://github.com/kogeler/ssh-wrapper/blob/main/SECURITY.md)
- [Security design](https://kogeler.github.io/ssh-wrapper/user/security/)
- [MIT license](https://github.com/kogeler/ssh-wrapper/blob/main/LICENSE)
