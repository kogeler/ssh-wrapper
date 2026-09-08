# Changelog

All notable changes to this independent package are documented here.

## Unreleased

## [0.1.1] - 2026-09-08

### Fixed

- Clean every surviving member of an owned remote process group, including
  descendants of an exited leader and children that ignore SIGTERM; observe
  natural exit and termination without waiting for the next heartbeat.
- Reject non-finite remote timeouts and preserve timeout precision when
  encoding the supervisor command.
- Make master and remote startup/closure single-use under concurrency and safe
  under cancellation, reclaiming late subprocess handles and joining cleanup.
- Bound and reap control and session probes, including orphaned pipe holders;
  enforce readiness deadlines and keep startup filesystem failures path-free.
- Decode systemd environment values as data and validate recovered runtime
  directories; reject unsafe scoped IPv6 authorities and invalid retention limits.
- Preserve foreground ownership and mux stdin despite conflicting SSH defaults;
  disable tunnel forwarding and reserve OpenSSH's temporary mux-path suffix.
- Reuse one live scenario for ordinary and FIDO acceptance with the SSH server
  confined to a pinned test container. Keep the client and hardware token on the
  host, remove host server provisioning from CI, and check remote PIDs only in
  the container namespace. Missing prerequisites fail instead of skipping.
- Package the live server's init process inside the pinned image and disable
  engine init injection, removing the hidden host `catatonit`/`docker-init`
  requirement while verifying orphan reaping in the shared live scenario.
- Allow exact resolver bootstrap updates before regenerating old locks, then
  validate all direct and bootstrap overlaps at the end of the shared Make gate.
- Use direct per-container pasta for rootless Podman live tests instead of a
  forced shared bridge, avoiding its Ubuntu network-helper teardown failure.
  Select networking from engine metadata, preserve Docker support and loopback
  publication, and keep all startup and cleanup failures blocking without
  changing host AppArmor profiles or requiring elevated privileges.

### Added

- Expose bounded engine diagnostics through `ACCEPTANCE_DEBUG=1` on the shared
  live Make targets without changing their network or security policy.
- Add an explicit operator-assisted `make test-fido` loopback gate using an
  existing security key, without modifying credentials or selecting it in CI.
- Expose the machine-local environment path through `make venv-path` and align
  API, lifecycle, security, release, and maintainer documentation with the code.

### Changed

- Update Ruff to 0.16.6 and build to 1.6.0, including the isolated resolver
  bootstrap, and refresh all four generated dependency graphs and hashes.
- Run container validation through one shared Make recipe that clears inherited
  private D-Bus addresses, preserving native host service discovery and failing
  on engine errors without ad-hoc cgroup or event backend overrides.
- Move direct maintainer dependencies to four native pip-compile `.in`/`.txt`
  pairs for Dependabot, omit internal package extras, and validate lock drift
  without upgrading the committed graph.
- Allow maintenance at an already published version while `Unreleased` notes
  accumulate; verify complete releases against their tagged source and skip
  reusable release CI and publication when no work remains.
- Isolate all five checkout tool environments by a project-specific hash of
  the OS machine ID and local UID, with separate CPython minor directories.
  Preserve legacy environments and other machines' environments during cleanup.

## [0.1.0] - 2026-08-30

- Extract the validated OpenSSH authority and ControlMaster lifecycle into the
  independent `ssh-wrapper` distribution.
- Provide heartbeat-supervised ownership of one remote process group.
- Recover only the allowlisted Linux user-session variables needed for initial
  interactive SSH authentication.
- Publish complete PyPI metadata from one `.version` source and mark the
  standard-library-only CPython 3.13 and 3.14 distribution for strict
  downstream type checking.
- Add four disjoint audience-specific hash locks, one pyproject-owned resolver
  bootstrap, exact vulnerability review, deterministic dependency snapshots,
  and wheel-only resolution checks; keep the packaging audience limited to
  standard wheel and sdist tooling.
- Build reproducible normalized wheel and sdist artifacts, verify their exact
  inventories, and clean-install and type-check both outside the source tree.
- Add evidence-backed API, security, compatibility, dependency, package, and
  CI/release contracts plus a strict offline-audited GitHub Pages site.
- Add event-separated CI, dependency submission, Pages, PR-body, and release
  workflows using Ubuntu 26.04 and immutable third-party revisions; give each
  library gate one owner and hand CI-built distributions directly to release.
- Publish through PyPI Trusted Publishing and reuse the same gated
  distributions for a fail-closed matching GitHub Release.
- Exercise one-auth, mux-only, no-fallback, bounded-diagnostic, and selective
  owned-process cleanup behavior against an ephemeral loopback OpenSSH server.
