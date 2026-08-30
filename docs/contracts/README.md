# Contract Catalog

Only this directory defines normative product guarantees. User and maintainer
documentation explains how to use and preserve them without creating a second
source of truth.

| Contract | Namespace | Owner |
| --- | --- | --- |
| [Package and distributions](package.md) | `PKG` | PyPI metadata, artifacts, and installation |
| [Dependencies](dependencies.md) | `DEP` | Direct pins, locks, audit, and snapshots |
| [CI and releases](ci_releases.md) | `CIR` | Automation topology and publication |
| [Security](security.md) | `SEC` | Authentication, mux isolation, and cleanup |
| [Public API](api.md) | `API` | Imports, types, errors, and ownership objects |
| [Compatibility](compatibility.md) | `CMP` | Python, Linux, OpenSSH, and acceptance |

Assertion IDs are permanent. Each assertion links to one or more exact test
nodes that serve as executable evidence.
