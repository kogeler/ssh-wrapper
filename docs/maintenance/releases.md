# Releases

## Version and artifacts

`.version` is the only human-maintained stable version. It is canonical
`X.Y.Z`; dynamic wheel and sdist metadata, `ssh_wrapper.__version__`, and one
dated changelog section derive from it. `tools/version.py` is the single local
owner for version validation and exact release-note rendering.

Build and inspect a candidate with:

```bash
make version-check
make release-notes
make package
make smoke
make reproducibility
```

The build creates exactly one wheel, one normalized sdist, and
`dist/SHA256SUMS.txt`. Equivalent clean source trees produce identical bytes.
Both archives are clean-installed outside the source tree and checked for
runtime import, version metadata, public API, lifecycle construction, and
strict installed typing.

## Publication state

The tag is `vX.Y.Z`, and the GitHub release has the same name. Its target is the
direct `main` commit, its body is the exact current changelog section, and its
assets are exactly the wheel, sdist, and checksum inventory.

The direct-main release workflow independently inspects PyPI files and GitHub
tag/release state while reusable CI runs once for the same commit. CI's
distribution job builds, smokes, and conditionally uploads one immutable
workflow artifact for the trusted release caller. The release workflow never
rebuilds it: PyPI Trusted Publishing and the GitHub release consume those same
bytes in order. An already published state is an exact verified no-op.
Conflicting names, versions, yanked state, targets, notes, sizes, or hashes stop
recovery without replacing history.

## Operator setup and sequence

The repository needs a GitHub Environment named `pypi`, with deployment
protection chosen by the operator. PyPI Trusted Publishing is bound to
`kogeler/ssh-wrapper`, workflow `release.yml`, and environment `pypi`; there is
no stored PyPI credential.

Configure GitHub Pages to use GitHub Actions as its source. Enable private
vulnerability reporting before publishing the security guidance. Protect
`main` with pull-request and code-owner review, conversation resolution, and
blocks on force pushes and branch deletion. Require every stable CI job:

- `Source quality and repository policy`
- `Compatibility and coverage (Ubuntu 26.04, CPython 3.13)`
- `Compatibility and coverage (Ubuntu 26.04, CPython 3.14)`
- `Wheel and sdist installation`
- `Hermetic real OpenSSH acceptance`
- `Dependency review and exact-lock audit`
- `CodeQL (actions)`
- `CodeQL (python)`
- `Exact version progression`

The path-filtered `Strict offline documentation build` must pass on
documentation changes; do not configure it as an unconditional status check
for pull requests that do not start the Documentation workflow.

After reviewing a clean candidate tree, the operator creates the first commit
on `main`, completes these settings, and pushes. The workflows perform
publication only from trusted direct-main state. See the
[CI and release contract](../contracts/ci_releases.md) for exact permission and
recovery rules.
