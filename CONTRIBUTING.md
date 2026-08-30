# Contributing

Keep changes scoped to this independent library. Read the affected assertion
in the [contract catalog](docs/contracts/README.md), update its exact evidence
with any observable behavior change, and follow the
[development procedure](docs/maintenance/development.md).

For ordinary changes, run:

```bash
make format
make check
```

Before handoff, run `make ci`; changes to live OpenSSH behavior also run
`make test-acceptance`. Dependency changes follow the
[dependency procedure](docs/maintenance/dependencies.md), and release changes
follow the [release procedure](docs/maintenance/releases.md).

Do not hand-edit generated requirement locks. Keep `.version`, the matching
dated `CHANGELOG.md` section, metadata, tests, and documentation synchronized.
