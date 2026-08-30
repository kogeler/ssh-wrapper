# Changelog

All notable changes to this independent package are documented here.

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
