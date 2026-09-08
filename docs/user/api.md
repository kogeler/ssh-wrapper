# Public API

Every supported root import is listed here. Imports from implementation
submodules are not part of the documented compatibility surface.

| Root import | Role |
| --- | --- |
| `SESSION_ENVIRONMENT_VARIABLES` | Exact Linux session-recovery allowlist |
| `BoundedTail` | Bounded byte-tail storage |
| `ConnectionMode` | Alias/direct authority enum |
| `ConnectionSpec` | Immutable validated SSH authority |
| `ConnectionState` | One-way master lifecycle enum |
| `OpenSSHMaster` | One native ControlMaster owner |
| `OwnedRemoteProcess` | One heartbeat-supervised remote process-group owner |
| `SSHError` | Stable expected-failure representation |
| `SSHMasterSettings` | Immutable native-client and liveness settings |
| `__version__` | Installed distribution version |
| `build_remote_supervisor_program` | Encoded remote-supervisor command builder |
| `resolve_session_environment` | Narrow asynchronous Linux session recovery |

## Connection values

The preferred constructors are:

```text
ConnectionSpec.from_alias(ssh_alias: str) -> ConnectionSpec
ConnectionSpec.from_direct(host: str, user: str, port: int = 22) -> ConnectionSpec
```

The dataclass constructor also accepts `ConnectionSpec(mode, ssh_alias=None,
host=None, user=None, port=None)`. Pass a `ConnectionMode` enum and exactly one
complete alias or direct authority; mixed or incomplete values raise `SSHError`.

An alias delegates host, proxy, identity, and host-key policy to trusted
OpenSSH configuration. A direct value validates a conservative host or IP,
user, and port while keeping them in separate argv fields. A resulting value
exposes `mode`, `ssh_alias`, `host`, `user`, `port`, `destination`,
`ssh_options`, `rsync_target`, `cache_key`, and `display_target`.

`ConnectionMode` has `ALIAS = "alias"` and `DIRECT = "direct"`.
`ConnectionState` has `NEW`, `STARTING`, `READY`, `LOST`, `CLOSING`, and
`CLOSED`, with matching lowercase string values.

## Master ownership

`SSHMasterSettings` accepts these fields and defaults:

| Field | Type | Default |
| --- | --- | --- |
| `ssh_path` | `Path` | required trusted executable path |
| `false_path` | `Path` | required trusted failing executable path |
| `connect_timeout` | `float` | required |
| `server_alive_interval` | `int` | `15` |
| `server_alive_count_max` | `int` | `3` |
| `runtime_prefix` | `str` | `"remote-ssh"` |

These settings are trusted caller inputs rather than authority values validated
by `ConnectionSpec`. Use absolute trusted executable paths, a positive finite
connect timeout, nonnegative integer OpenSSH keepalive values, and
a non-empty filename prefix with no path separator for `runtime_prefix`.
Invalid timeout, keepalive, or prefix values raise `ValueError`; executable or
runtime startup failures use `SSHError` without exposing their private paths.

Create the owner with:

```text
OpenSSHMaster(settings, connection, *, runtime_base: Path | None = None)
```

`runtime_base` is primarily useful to an embedding application that already
owns an existing, writable, searchable, secure runtime parent. Normal callers
leave it unset. The documented members are `settings`, `connection`, `state`,
and these operations:

- `await start()` authenticates at most once and waits for mux readiness.
- `await ensure_ready()` checks that the existing mux remains usable.
- `mux_transport_argv()` returns no-destination, no-fallback transport argv.
- `command_argv(remote_program)` appends one destination and remote program.
- `mux_ssh_command()` and `rsync_ssh_command()` return a quoted transport.
- `create_mux_wrapper(name="mux-ssh")` creates a private executable wrapper.
- `await close()` terminates and reaps owned local state; repeated closure is
  safe.

`runtime_dir`, `control_path`, and `process` expose the owned runtime paths and
local subprocess (initially `None`). Observe them without changing ownership.
After close, a recorded runtime path may remain available as a value even though
the directory has been removed. Concurrent closes wait for the same cleanup;
closing during startup cancels that start. Cancellation of `start()` or `close()`
finishes owned cleanup before propagating `CancelledError`.

Mux construction requires runtime state created by this owner. The caller owns
ordinary secondary subprocesses created from the returned vectors.
`command_argv(remote_program)` takes a remote shell program, not a list of child
arguments. Quote application arguments for that remote shell, or use
`OwnedRemoteProcess` for argv encoded as data. Consumer-appended SSH options are
trusted inputs, not an interface for untrusted authority strings.

## Remote ownership and bounded data

Construct an owned remote child with:

```text
OwnedRemoteProcess(
    master,
    argv: tuple[str, ...],
    *,
    heartbeat_interval: float,
    lease_timeout: float,
    grace_timeout: float,
    tail_bytes: int = 16384,
)
```

The three timeouts are required and validated as positive and finite. Choose a
heartbeat interval comfortably shorter than the lease to allow for scheduling
and transport delays. `tail_bytes` is a positive integer retention bound; invalid
values raise `ValueError`, and the default is 16 KiB.
The object exposes a fixed 4 KiB `stdout_head`, bounded `stdout_tail` and
`stderr_tail`, and the local mux `returncode`. `await start()` is single-use,
`await wait()` observes completion and finishes bounded output draining, and
`await close()` releases ownership. Cancelling `wait()` only stops that wait:
heartbeats and the child continue, so use `close()` in a `finally` block to release
ownership. Cancelling a start or close finishes cleanup before propagating.
`process` exposes the local mux subprocess, initially `None`.

`BoundedTail(limit: int = 16384, data: bytes = b"")` provides `append(chunk)`,
`clear()`, `text()`, and the retained `data`. Its documented input contract
requires a positive integer `limit` and initial `data` no longer than that limit;
invalid initial values raise `ValueError`. `append()` also rejects an invalid
mutated limit and clips oversized chunks without retaining the whole chunk.

`build_remote_supervisor_program(argv, *, lease_timeout, grace_timeout)`
returns the fixed remote Python command with child argv encoded as data. The
argv must be non-empty, contain at most 256 strings, and contain no NUL. Direct
callers also supply positive, finite timeouts; both entry points validate them.

## Errors, environment, and version

`SSHError(code, message, details)` exposes those three attributes and
`to_dict()`. Omitting `details` creates a fresh empty map, and empty details do
not appear in the serialized result. Public master errors intentionally omit
raw SSH stderr and private paths.

`await resolve_session_environment(base_environment=None)` returns a copy of
the supplied mapping or current process environment. On Linux it can recover
only names in `SESSION_ENVIRONMENT_VARIABLES`; it never mutates `os.environ`.

`__version__` reads `.version` in a source checkout and the `ssh-wrapper`
distribution metadata in an installed package. If neither source version nor
installed metadata is available, it reports `0.0.0+unknown`. The
[normative API contract](../contracts/api.md) ties each guarantee
to an automated test.
