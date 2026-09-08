# Security Maintenance

## Review focus

Changes to SSH argv, lifecycle transitions, stderr handling, environment
recovery, runtime paths, or remote supervision receive direct invariant tests.
Review exact process arguments and state changes rather than only successful
output.

OpenSSH configuration remains trusted input so host-key verification, proxy
routing, identities, and system prompts keep their native behavior. Secondary
channels retain explicit no-authentication and false-proxy barriers. A lost
master object is terminal.

## Diagnostics and environment

Public master failures stay path-free and never copy raw stderr. Drains remain
bounded and continuous. Session probes use bounded output, short timeouts, new
local process groups, an exact allowlist, owned absolute runtime paths, and no
global environment mutation.

Remote program argv remains data encoded exactly once. Supervision owns a
single new remote process group and cannot broaden cleanup to other groups or
users.

## Acceptance isolation

The Linux acceptance test keeps the native SSH client on the host and runs the
server as an unprivileged user in a throwaway container. Host `sshd` is neither
required nor installed. Make builds the test-only image from
`tests_acceptance/server/Containerfile`, whose base digest and signed Debian
snapshot pin its toolchain; the first build requires network access and later
builds reuse the engine cache. No test image is published or packaged.

The image also installs `tini` from that signed snapshot and runs it as PID 1
to forward signals and reap orphaned children. The fixture explicitly uses
`--init=false`, so Podman/Docker never needs to find or mount an init binary
from the host, even if engine defaults enable init injection. In particular,
`lookup init binary: catatonit ... not found` is a test-fixture dependency error,
not a reason to install another host package or change the operator's `PATH`.
Both live gates verify PID 1 and orphan reaping before client authentication.

The ordinary gate creates a fresh client key, writes an isolated SSH
configuration and known-hosts entry, and disables agent use and unrelated
identities.
The server generates its own fresh host key inside the container. Only the
client's public authorization key is passed in; there are no checkout, identity,
agent-socket or hardware-device mounts. Its root filesystem is read-only,
capabilities are dropped, and no-new-privileges is enabled. The engine publishes
an unused port only on host `127.0.0.1`, without a racy host-side reservation.
Before creation, engine metadata selects direct per-container `pasta` for
rootless Podman or the native Docker bridge. Podman never uses a forced shared
bridge; rootful Podman is rejected with instructions to run without `sudo`.
There is no network fallback or change to host AppArmor policy. Startup and
teardown errors remain blocking, including failures to remove the container.
It exercises the real library, verifies one accepted authentication and one
master, kills that master to prove no fallback, and checks that only the owned
remote group is cleaned.
It also exercises conflicting native background/stdin/session/tunnel settings,
literal percent characters, and the maximum safe mux pathname length.

Both `make test-acceptance` and `make test-fido` call the existing shared live
scenario and the same container fixture. Remote Python, PID-file reads,
process-group inspection and signals all run inside that container: a container
PID is never used in a host kill operation. The fixture removes only its unique
owned container, including after a failed or cancelled startup. Startup is
observed through engine logs, without adding an SSH connection or authentication.

GitHub CI calls the same `make test-acceptance` target without provisioning a
host server. `make ci` includes this gate once. Engine subprocesses use the same
D-Bus cleanup as workflow validation; the native client's session environment
and prompt routing are unchanged. Missing required tools and server failures
fail the requested gate instead of reporting a successful skip.

All subprocesses and temporary material are reaped on success, assertion
failure, timeout, and cancellation. Ordinary tests remain network-blocked and
independent of live Linux session services. The
[security contract](../contracts/security.md) is the normative source.

## Operator-assisted FIDO check

Run ordinary checks and `make test-acceptance` first. Then coordinate with the
operator before running in their normal graphical login session, without `sudo`:

```bash
make test-fido FIDO_IDENTITY=/absolute/path/to/id_ed25519_sk
```

Use an existing OpenSSH `ed25519-sk` or `ecdsa-sk` identity with its matching
`.pub` file and an available physical authenticator. The test never generates,
rewrites, or copies the hardware credential. It creates temporary symlinks to
the selected identity on the host, and passes only its public key to the
container server. Existing server configuration, authorized keys, and known
hosts are untouched. The host needs CPython 3.13 or 3.14, the OpenSSH client tools
and a working Podman or Docker engine, not an OpenSSH server. Authentication
uses the native local agent or security-key provider and recovered initial
session environment; no USB device or agent forwarding into the container is
needed.

The operator enters any PIN/passphrase in the native system prompt and touches
the key when requested, never in chat or a library API. The startup window is
120 seconds, starting only after the container server is ready. After one
accepted authentication, the same acceptance sequence checks mux commands,
owned cleanup and failure without fallback after master
loss; no second authentication is permitted. This hardware gate is not part of
`make ci`, ordinary tests, or automated acceptance and cannot be reported as
passed without the actual operator-assisted run.
