# Development

## Provenance and independence

Packaging, dependency, documentation, CI, and release automation were adapted
from reviewed `joplin-md-sync` commit
`53ce1d0584ecd015edaf5583aeed216ed7b28ca0`. That revision is design
provenance only. This repository never imports, executes, or reads another
checkout.

Permanent contract namespaces are `PKG`, `DEP`, `CIR`, `SEC`, `API`, and
`CMP`. Normative text lives only under [contracts](../contracts/README.md); user
and maintenance pages explain its use.

## Prerequisites and change loop

Use CPython 3.13 or 3.14. OpenSSH client/server commands are needed only for
the Linux acceptance gate, and Podman or Docker is needed for immutable
actionlint. Lock generation and the complete aggregate use CPython 3.14 as the
deterministic resolver host; CI runs the network-guarded tests separately on
both supported minors. The actionlint custom-label entry teaches its parser
the GitHub-hosted `ubuntu-26.04` preview label; it does not declare or require a
self-hosted runner.

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
make test-acceptance
```

`make quality` covers format, lint, strict types, Bandit, source compilation,
version agreement, and dependency ownership. `make policy` covers lock drift,
platform resolution, the offline dependency snapshot, and workflow lint.
`make check` adds the network-guarded unit suite. `make ci` aggregates each
quality, policy, coverage, documentation, audit, distribution, clean-install,
and reproducibility gate exactly once. GitHub CI assigns the same gates to
separate jobs instead of invoking the aggregate and repeating their work.

## Local state

Each `.venv-*` directory belongs to one dependency audience. Generated
environments, caches, site output, coverage, package output, and policy
artifacts stay untracked. `make clean` removes only the exact project-owned
paths listed in the Makefile.

Ordinary tests run through `tools/run_tests.py`, which blocks DNS plus
IPv4/IPv6 stream and datagram traffic before pytest loads tests. The loopback
OpenSSH suite is separate and explicit. See
[security maintenance](security.md) for its trust model.
