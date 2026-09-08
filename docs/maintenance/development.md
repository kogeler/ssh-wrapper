# Development

## Provenance and independence

Packaging, dependency, documentation, CI, and release automation were adapted
from reviewed `joplin-md-sync` commit
`53ce1d0584ecd015edaf5583aeed216ed7b28ca0`. That revision is design
provenance only. This repository never imports, executes, or reads another
checkout.

Native dependency inputs and release maintenance behavior also adapt reviewed
`elsewindow` PRs #4 and #5. The machine namespace design comes from the venv
portion of PR #8, scoped here to maintainer environments and both supported
Python minors. These are design references, with no checkout dependency.

Permanent contract namespaces are `PKG`, `DEP`, `CIR`, `SEC`, `API`, and
`CMP`. Normative text lives only under [contracts](../contracts/README.md); user
and maintenance pages explain its use.

## Prerequisites and change loop

Use CPython 3.13 or 3.14. The Linux acceptance gate needs the host OpenSSH client
tools (`ssh` and `ssh-keygen`), not a host server. Podman or Docker supplies both
immutable actionlint and the isolated test-only SSH server. Lock generation and
the complete aggregate use CPython 3.14 as the deterministic resolver host;
CI runs the network-guarded tests separately on
both supported minors. The actionlint custom-label entry teaches its parser
the GitHub-hosted `ubuntu-26.04` preview label; it does not declare or require a
self-hosted runner.

Node.js enables offline tests that execute the actual GitHub Actions release
scripts with fixture APIs. GitHub-hosted runners provide it; without a local
`node` command those JavaScript tests are reported as skipped.

For each atomic behavior change, update implementation, direct test, and owning
contract together. Run the narrow affected test immediately, then:

```bash
make format
make check
```

After dependency, documentation, workflow, packaging, or release-policy work,
run the applicable focused target and complete Linux validation:

```bash
make ci
```

`make quality` covers format, lint, strict types, Bandit, source compilation,
version agreement, and dependency ownership. `make policy` covers lock drift,
platform resolution, the offline dependency snapshot, and workflow lint.
`make check` adds the network-guarded unit suite. `make ci` aggregates each
quality, policy, coverage, ordinary live OpenSSH, documentation, audit,
distribution, clean-install, and reproducibility gate exactly once. GitHub CI
assigns the same gates to separate jobs instead of invoking the aggregate and
repeating their work.
Use `make test-acceptance-support` for the server fixture's service-independent
regressions and `make test-acceptance` for a focused real live run. The latter
and `make test-fido` both build their server through `make acceptance-image`.

## Container validation and host services

`make validate-actions` is the shared local and GitHub CI workflow-lint entry
point; the live targets use the same container environment policy. Run validation
through Make. A failing target is fixed in the target, its tests, and its owning
contract before reporting success; an individual
tool command or a one-off container backend override does not validate that
shared path.

A terminal or editor started inside an application with a private D-Bus session
can pass that private address to Podman and its OCI runtime. With the systemd
cgroup manager, this can produce `crun: sd-bus call: Process
org.freedesktop.systemd1 exited with status 1: Input/output error` even while
the host's user systemd manager is healthy. The same host may therefore work
from a normal login and fail from another application session.

The Make recipe removes `DBUS_SESSION_BUS_ADDRESS` and
`DBUS_SYSTEM_BUS_ADDRESS` only from the engine subprocess environment. Native
service discovery uses the host buses, including the user bus under
`XDG_RUNTIME_DIR`; the launching application's environment is unaffected.
Podman retains its configured cgroup manager and event backend, and startup
errors still fail the target. This behavior is covered by
[the container validation contract](../contracts/ci_releases.md#cir-014-local-and-ci-container-validation-share-one-make-boundary).

Live acceptance reads engine metadata before creating a server. Run Podman
rootless, with its `pasta` helper installed (the `passt` OS package). The fixture
uses direct `--network=pasta`; Docker keeps its native bridge. Both publish only
the test SSH port on host loopback and use the same Make targets locally and in CI.

The original host-server acceptance never exercised Podman networking, and
actionlint uses `--network=none`. Forcing the new container server through
`--network=bridge` activated Podman's shared rootless network namespace. On
affected Ubuntu installations its teardown can fail with
`rootless netns: kill network process: permission denied` because the host
AppArmor profiles block Podman from signalling the shared `pasta` helper.
Direct per-container pasta avoids that shared-bridge lifecycle. Do not disable
AppArmor, alter its profiles, add `sudo`, or suppress cleanup failures to pass
the test. Missing pasta or incompatible engine metadata fails explicitly;
there is no retry with bridge, host networking, or a different engine.
For engine diagnostics use `make test-acceptance ACCEPTANCE_DEBUG=1` (or the
same option with the operator-assisted FIDO target). It adds debug logging
without changing networking or security settings; retained engine stderr is
printed in tails limited to 4096 characters per command. Do not replace the
shared target with an ad-hoc run.

If direct pasta fails with `pasta failed with exit code -1`, inspect that debug
output first. For example, Podman may report that its own `pasta --version`
probe failed with `signal: segmentation fault`, before it configured any
container network. This is a helper startup failure, not evidence of the
shared-bridge signal-permission bug above. Keep the live gate failing and
investigate the host helper; do not hide it with a different network backend
or an AppArmor override.

## Local state

All five Make environments live under
`.venvs/<machine-user-key>/cpython-<major.minor>/`, with `dev`, `test`, `package`,
`docs`, and `lock` audiences. `tools/machine.py` runs with the selected `PY` in
isolated mode before using any prepared environment. It hashes `/etc/machine-id`
and the local UID in a project-specific namespace; missing or invalid identity
stops Make without falling back to a common directory.

Each machine can prepare its own environments in the same network-mounted
checkout. `make check PY=python3.13` and `make check PY=python3.14` also use
separate environments on one machine. To select an interpreter in an editor,
run `make venv-path PY=python3.14` and append `/dev/bin/python` or
`/test/bin/python` to the printed path.

Old `.venv` and `.venv-*` directories are left in place and are no longer used
by Make. Environment recreation and `make clean` affect only the selected
machine/user/interpreter audiences. Caches, site output, coverage, package
output, and policy artifacts remain checkout-wide untracked state; coordinate
build and cleanup commands when working concurrently. `make clean` removes
only the exact generated paths listed in the Makefile.

Ordinary tests run through `tools/run_tests.py`, which blocks DNS plus
IPv4/IPv6 stream and datagram traffic before pytest loads tests. The loopback
OpenSSH suite is separate and explicit. See
[security maintenance](security.md) for its trust model.

The separate `make test-fido` gate is operator-assisted and excluded from
automatic validation. Arrange the operator's participation only after ordinary
tests and loopback acceptance pass; its setup is described in
[security maintenance](security.md#operator-assisted-fido-check).
