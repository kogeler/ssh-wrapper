# Architecture

## Boundary

The package wraps native OpenSSH without replacing its configuration, host-key,
proxy, or authentication policy. `ConnectionSpec` validates authority,
`OpenSSHMaster` owns one master, and `OwnedRemoteProcess` owns one optional
remote process group. Runtime code has no consumer protocol and no third-party
Python import.

## Master lifecycle

`OpenSSHMaster.start()` creates a private runtime directory and starts one
`ssh -M -N` process in a new local process group. Readiness requires both its
Unix socket and a successful control check.
The mux path reserves OpenSSH's temporary binding suffix; literal percent
characters are escaped before native option expansion. Configuration cannot
background the owned client or enable tunnel forwarding.

```text
new -> starting -> ready -> closing -> closed
                   |
                   +-----> lost -> closing -> closed
```

There is no path back to `starting`. Every secondary command names the existing
socket, disables ControlMaster creation, disables authentication methods, and
uses a false proxy command. Transport forms omit the destination so mux-aware
consumers append their own structured arguments.
Startup and closure have private owned tasks. Closing interrupts a pending
startup; concurrent closes join one cleanup. Caller cancellation is propagated
after cleanup, including a process handle received during cancellation.

## Remote process ownership

The remote supervisor receives child argv as URL-safe base64 JSON and decodes
it as data. It starts the child in a new process group. Supervisor stdin is a
private ownership channel, not child stdin. EOF, a malformed heartbeat, lease
expiry, or termination stops only the owned group.
Natural leader exit also ends ownership of surviving group members. Escalation
checks the group, so an early-exiting leader cannot protect a descendant that
ignores SIGTERM. Short polling observes child exit and signals without waiting
for a heartbeat period.

Local drain tasks retain a bounded head or tail and continue reading so a noisy
child cannot deadlock on a full pipe. Local teardown closes the ownership
channel, waits for the remote grace period, and escalates only against the local
mux channel when necessary.

## Source layout

```text
ssh_wrapper/              typed runtime package
ssh_wrapper/_process.py   private local subprocess and cancellation ownership
tests/                    service-independent tests and policy evidence
tests_acceptance/         shared host-client/container-server live scenario
tests_acceptance/server/  test-only SSH server image and entry point
docs/contracts/           normative guarantees with evidence links
docs/user/                public usage guidance
docs/maintenance/         maintainer procedures and rationale
.github/workflows/        event-separated automation
tools/machine.py          maintainer environment namespace selector
requirements-*.in         four exact direct tool audiences
requirements-*.txt        four generated hash locks
```

The [API contract](../contracts/api.md) and
[security contract](../contracts/security.md) own normative behavior.
