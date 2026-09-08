# Releases

## Version and artifacts

`.version` is the only human-maintained stable version. It is canonical
`X.Y.Z`; dynamic wheel and sdist metadata, `ssh_wrapper.__version__`, and one
dated changelog section derive from it. `tools/version.py` is the single local
owner for version validation and exact release-note rendering.

Ordinary changes retain the published `.version` and accumulate release-worthy
notes under `## Unreleased`. Multiple merged PRs can share that section.
Deliberate release preparation advances `.version`, moves accumulated entries
into the matching dated section, and leaves an empty `Unreleased` heading.

When a PR changes `CHANGELOG.md`, the trusted PR metadata workflow mirrors its
newest populated level-two section, normally `Unreleased`, into one managed
body block. A version change is not required. Manual text outside the markers
is preserved; malformed markers and concurrent body edits stop synchronization.

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

Every direct-main push first inspects PyPI files and GitHub tag/release state.
If the current version is already fully and exactly published, reusable release
CI and both publication jobs are skipped. Published metadata is checked against
the immutable tagged source, so later main commits and accumulated `Unreleased`
notes do not conflict with the original release. Ordinary PR CI still validates
those changes and permits retaining an already published stable version.

When publication work is needed, reusable CI runs once for the release commit. CI's
distribution job builds, smokes, and conditionally uploads one immutable
workflow artifact for the trusted release caller. The release workflow never
rebuilds it: PyPI Trusted Publishing and the GitHub release consume those same
bytes in order. Draft recovery remains tied to the current release commit.
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

After reviewing the release candidate and completing these settings, the
operator merges or deliberately advances the release commit onto `main` and
pushes it through the repository's review process. The workflows perform
publication only from trusted direct-main state. See the
[CI and release contract](../contracts/ci_releases.md) for exact permission and
recovery rules.
