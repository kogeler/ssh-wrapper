# Usage

## Own one master

The caller selects an OpenSSH authority and supplies trusted executable paths.
An alias delegates host, proxy, host-key, and identity policy to normal OpenSSH
configuration:

```python
import asyncio
from pathlib import Path

from ssh_wrapper import ConnectionSpec, OpenSSHMaster, SSHMasterSettings


async def hostname() -> bytes:
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
            *master.command_argv("hostname"),
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await process.communicate()
        if process.returncode:
            raise RuntimeError(f"remote command exited {process.returncode}")
        return stdout
    finally:
        await master.close()
```

Direct authority is also available when configuration aliases are not wanted:

```python
connection = ConnectionSpec.from_direct("203.0.113.10", "deploy", 22)
```

The destination, user, and port remain distinct argv values. A direct host does
not opt out of OpenSSH host-key checking.

## Use mux-aware consumers

`master.mux_transport_argv()` returns SSH options without a destination.
`master.command_argv(remote_program)` appends one destination and remote
program. `master.mux_ssh_command()` is a shell-escaped transport string for a
mux-aware consumer, and `master.create_mux_wrapper()` creates a private
executable wrapper when a consumer accepts only a path.

These forms contain explicit barriers against new authentication and proxy
fallback. If the master disappears, construct a new `OpenSSHMaster` only after
your application deliberately decides to authenticate again.

## Own a long-lived remote child

Use `OwnedRemoteProcess` only when the remote target provides `python3` and the
child should remain tied to a heartbeat lease:

```python
from ssh_wrapper import OpenSSHMaster, OwnedRemoteProcess


async def supervise(master: OpenSSHMaster) -> None:
    owned = OwnedRemoteProcess(
        master,
        ("worker", "--mode", "safe"),
        heartbeat_interval=5,
        lease_timeout=20,
        grace_timeout=5,
    )
    await owned.start()
    try:
        # Inspect owned.stdout_head, owned.stdout_tail, or owned.stderr_tail.
        await owned.wait()
    finally:
        await owned.close()
```

Application arguments are encoded as data. Supervision creates and cleans one
remote process group; it does not kill unrelated processes or a daemon that
intentionally escapes that group.

The default diagnostic tail is 16 KiB. If `tail_bytes` is customized, pass a
positive integer so stdout and stderr retention stays bounded.

See the [API guide](api.md) and [security guide](security.md) for the ownership
and diagnostic boundaries.
