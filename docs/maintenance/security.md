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

The Linux acceptance test creates fresh client and server keys in a temporary
directory, writes an isolated SSH configuration and known-hosts entry, starts
an unprivileged loopback sshd, and disables agent use and unrelated identities.
It exercises the real library, verifies one accepted authentication and one
master, kills that master to prove no fallback, and checks that only the owned
remote group is cleaned.

GitHub's Ubuntu runner supplies the client but not the server command. The
acceptance job installs `openssh-server` at the exact installed
`openssh-client` Debian version, verifies the match, and uses it only as this
ephemeral loopback fixture.

All subprocesses and temporary material are reaped on success, assertion
failure, timeout, and cancellation. Ordinary tests remain network-blocked and
independent of live Linux session services. The
[security contract](../contracts/security.md) is the normative source.
