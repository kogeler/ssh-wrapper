# SSH Wrapper Agent Guide

This file is the entry point for agents changing this independent project.
Read the relevant documents before editing behavior.

## Documentation map

- `README.md` is the concise public overview.
- `CONTRIBUTING.md` and `SECURITY.md` are GitHub-facing routes into the
  maintained development and security documentation.
- `docs/contracts/` is the only normative contract catalog; every assertion
  has a permanent ID and an exact automated evidence node.
- `docs/user/` provides public installation, usage, API, and security guidance.
- `docs/maintenance/` provides architecture, dependency, development, release,
  and security procedures. Update the owning contract with every policy change.
- `.version` is the only human-maintained version; dynamic package metadata,
  `ssh_wrapper.__version__`, and `CHANGELOG.md` must resolve to the same release.
- `requirements-{dev,test,package,docs}.in` own exact direct tool dependencies;
  their matching `.txt` files are generated hash locks and native Dependabot
  pairs. Root `pyproject.toml` owns empty runtime metadata and the isolated
  resolver bootstrap; maintainer audiences are not published as package extras.
- Ordinary changes retain `.version` and accumulate notes under `Unreleased`.
  Only deliberate release preparation advances the version and its dated notes.
- `.github/workflows/` owns untrusted-change CI with narrowly scoped security
  reporting, trusted dependency submission, and fail-closed release publication
  for this independent repository.

Keep all local documentation links relative. Do not add assumptions about a
parent repository or consumer-specific files.

## Code map

- `ssh_wrapper/connection.py` validates authority and owns one OpenSSH master.
- `ssh_wrapper/session_environment.py` recovers a narrow allowlist for the
  initial authentication subprocess.
- `ssh_wrapper/remote_process.py` owns one heartbeat-supervised remote process
  group over an existing mux.
- `ssh_wrapper/bounded.py` owns bounded diagnostic storage.
- `ssh_wrapper/_process.py` owns private cancellation-safe subprocess cleanup.
- `ssh_wrapper/errors.py` defines the stable library error type.
- `tests/` contains service-independent tests and must never import a consumer.
- `tests_acceptance/` owns one shared Linux live scenario with a native host
  client and an unprivileged container server. Never require host `sshd`.
  The test-only server image and entry point live in `tests_acceptance/server/`;
  only a public authorization key crosses the boundary, never a client identity,
  agent socket, hardware device, or checkout mount. Inspect remote PIDs only
  inside that container, never through host process operations.
  The image owns PID 1 and orphan reaping. Disable engine init injection;
  never require host `catatonit` or `docker-init` for the live tests.
  Inspect engine metadata before starting the server. Podman live tests require
  rootless mode and direct per-container `pasta`, never a forced bridge. Docker
  retains its native bridge. Keep publication on host loopback, propagate
  cleanup failures, and never retry with host networking or weaker security.
  `make test-fido` is separate and requires the operator's explicitly selected
  FIDO identity and physical/native-prompt interaction; never run it unattended.
- `Makefile` installs each tool audience only from its matching hash lock.
- `tools/machine.py` selects all five Make environments beneath
  `.venvs/<machine-user-key>/<interpreter>/` before any venv is used.

## Required invariants

- Starting a master performs at most one deliberate SSH authentication.
- Losing a master never reconnects or starts another authentication.
- Secondary channels use the existing private control socket and cannot fall
  back to a new connection.
- Forwarding, agent sharing, X11 forwarding, remote commands from SSH config,
  and local SSH commands remain disabled.
- Standard OpenSSH configuration remains trusted input so host-key checking,
  proxy configurations, and system authentication prompts continue to work.
- Only the documented session-environment allowlist may be recovered, inherited
  non-empty values win, and the recovered environment is passed only to the
  initial master subprocess.
- Master stderr is drained continuously and retained only in bounded memory.
  Public errors never expose raw stderr or private paths.
- A supervised child is started in a new remote process group. Owner EOF,
  malformed heartbeat, lease expiry, cancellation, and local teardown clean
  only that group.
- Runtime code has no third-party Python dependency and no consumer-specific
  protocol, application, container, test-harness, or response-schema knowledge.
- Never hand-edit a generated requirements lock or remove its pip-compile
  header. Change an exact direct dependency in its owning `.in` file and
  regenerate the affected lock mechanically.
  Update overlapping resolver bootstrap pins in `pyproject.toml` together.
  Bootstrap export reads source pins, not the old locks; generation validates
  all four new locks and bootstrap overlaps before succeeding.
- Missing or invalid OS machine identity fails without a shared venv fallback.
  Environment recreation and cleanup leave legacy and other owners' venvs intact.
- Workflow actions use immutable commit SHAs. Each workflow job calls only its
  scoped project-owned Make contract; `make ci` aggregates those contracts once
  for complete local validation.
- Run project tools, tests, and validation through the owning Make targets.
  Never treat an ad-hoc engine/backend override or a direct tool invocation as
  a substitute for a failed target. Fix the shared target, regression evidence,
  and owning contract, then verify the ordinary local and CI entry points.
- Container validation and acceptance clear inherited D-Bus address overrides only for the
  engine subprocess, so private application buses cannot redirect host systemd
  access. Keep native cgroup and event backends and propagate failures.
- Dependency findings must exactly equal the reviewed exception set. A new
  finding and a stale exception both fail.
- `.version` is the only human-maintained release version. Version mirrors,
  changelog section, tag, release target, name, and notes must agree exactly.
- An exact complete published version skips reusable release CI and publication,
  even after main advances. Validate published metadata against its tagged source;
  drafts remain tied to the proposed release commit. PR-body automation mirrors
  populated `Unreleased` notes without requiring a version change.
- Untrusted pull-request code runs with read-only repository permissions.
  Security-event, dependency-submission, PR-metadata, Pages, OIDC, and final
  release writes remain narrowly confined to their owning jobs.

## Development workflow

```bash
make format
make check
make ci
```

Run the smallest relevant test immediately after an atomic change. Run the
complete check before handoff. Do not lower coverage or weaken a test to hide a
failure.

Use `apply_patch` for source edits. Preserve unrelated work. Never create a
commit unless the user explicitly requests one in the current conversation,
and never push as part of an automated change.
