# Security

## Trusted inputs

The caller chooses the SSH authority and supplies paths to trusted `ssh` and
`false` executables. A configuration alias can use normal OpenSSH host-key,
proxy, identity, and system-prompt policy. Treat that configuration as trusted
input. The library does not accept passwords, PINs, private-key contents, or
agent data through its API.

## One authentication and isolated channels

A master object starts no more than one deliberate authentication subprocess.
Its control socket is placed in a newly created mode-`0700` directory.
Secondary vectors disable new authentication, forwarding, agent sharing, X11,
configured local commands, configured remote commands, and proxy fallback.
Master loss is terminal for that object.

## Linux session recovery

Interactive authentication sometimes needs routing values from the active
Linux user session. The library can probe `loginctl` and
`systemctl --user show-environment` to fill only this allowlist:

```text
DISPLAY
WAYLAND_DISPLAY
XAUTHORITY
XDG_RUNTIME_DIR
DBUS_SESSION_BUS_ADDRESS
SSH_AUTH_SOCK
SSH_ASKPASS
SSH_ASKPASS_REQUIRE
```

Inherited non-empty values win. The recovered runtime directory is accepted
only when it is absolute, exists, and belongs to the current UID. Recovered
values go only to the initial master subprocess and never mutate `os.environ`.
Non-Linux platforms and unavailable probes simply retain the inherited copy.

## Diagnostics and remote cleanup

Master stderr is drained continuously into bounded memory. Known interactive
prompt failures receive a stable message; other failures expose only an exit
status. Raw stderr, control paths, executable arguments, and identity paths do
not enter public master errors.

Remote stdout and stderr evidence is also bounded, but applications still need
to decide whether it is safe to display. The remote supervisor terminates only
the process group it created. It cannot clean a daemon that deliberately
escapes that group or a process blocked by kernel state.

Report suspected vulnerabilities privately through the repository's GitHub
security advisory interface. Do not include credentials, identity files, or
private host data in a public issue. The [security contract](../contracts/security.md)
defines the executable invariants.
