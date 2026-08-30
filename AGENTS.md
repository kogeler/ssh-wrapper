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
- `requirements-{dev,test,package,docs}.txt` are generated hash locks.
  Root `pyproject.toml` owns every exact direct Python dependency.
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
- `ssh_wrapper/errors.py` defines the stable library error type.
- `tests/` contains service-independent tests and must never import a consumer.
- `tests_acceptance/` owns the isolated Linux loopback OpenSSH gate.
- `Makefile` installs each tool audience only from its matching hash lock.

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
  header. Change an exact direct dependency in its owning project file and
  regenerate the affected lock mechanically.
- Workflow actions use immutable commit SHAs. Each workflow job calls only its
  scoped project-owned Make contract; `make ci` aggregates those contracts once
  for complete local validation.
- Dependency findings must exactly equal the reviewed exception set. A new
  finding and a stale exception both fail.
- `.version` is the only human-maintained release version. Version mirrors,
  changelog section, tag, release target, name, and notes must agree exactly.
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
