# Dependency Contract

## Assertions

### `DEP-001` - Native pip-compile inputs own direct tool dependencies

**Contract:** Runtime dependencies MUST remain empty. Exactly four non-empty
`requirements-{dev,test,package,docs}.in` files MUST own exact direct audience
pins, without includes, markers, ranges, or duplicate requirements. Their
same-stem `.txt` locks MUST be native Dependabot pip-compile pairs;
`pyproject.toml` MUST be excluded from Dependabot's pip manifests and MUST NOT
publish maintainer extras. Its standard dependency-groups table MUST own the
exact isolated resolver bootstrap. The build-system requirement MUST express
backend capability, with the exact build backend pinned in the package input.
Direct audience dependencies MUST be disjoint. The packaging audience MUST
contain only the tools needed to create a standard wheel and sdist; installed-package
type smoke MUST reuse the quality audience's type checker.

**Evidence:**

- [`test_direct_dependencies_are_exact_and_scoped`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_direct_dependencies_are_exact_and_scoped`
- [`test_runtime_imports_only_standard_library_or_local_modules`](../../tests/test_project_boundary.py) - `tests/test_project_boundary.py::test_runtime_imports_only_standard_library_or_local_modules`
- [`test_native_inputs_reject_nonexact_or_ambiguous_requirements`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_native_inputs_reject_nonexact_or_ambiguous_requirements`
- [`test_native_inputs_reject_duplicate_owners_and_extra_audiences`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_native_inputs_reject_duplicate_owners_and_extra_audiences`
- [`test_repository_automation_configuration_is_project_local`](../../tests/test_project_policy.py) - `tests/test_project_policy.py::test_repository_automation_configuration_is_project_local`

### `DEP-002` - Exactly four generated hash locks exist

**Contract:** `requirements-dev.txt`, `requirements-test.txt`,
`requirements-package.txt`, and `requirements-docs.txt` MUST be the only Python
locks. Every lock MUST be non-empty, retain its pip-compile header, and attach
one or more SHA-256 hashes to every exact pin.

**Evidence:**

- [`test_all_committed_locks_are_nonempty_pip_compile_hash_locks`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_all_committed_locks_are_nonempty_pip_compile_hash_locks`

### `DEP-003` - Audience installation is hash-verified and wheel-only

**Contract:** Supported development environments MUST install their matching
lock with `--require-hashes --only-binary=:all:` and MUST run `pip check`.
Resolver bootstrap versions MUST be exact, read from the standard
`[dependency-groups].resolver-bootstrap` table, isolated from audience
environments, installed without transitive resolution, and match every
overlapping frozen audience version.
Bootstrap export MUST validate its exact source pins without reading existing
audience locks, so updating an overlapping package does not require the new
resolver to match the old graph before regeneration. `make lock` and
`make refresh-dependencies` MUST validate all direct and bootstrap overlaps
after generating all four locks, and MUST fail on any remaining mismatch.

**Evidence:**

- [`test_make_exposes_every_governance_boundary`](../../tests/test_project_policy.py) - `tests/test_project_policy.py::test_make_exposes_every_governance_boundary`
- [`test_direct_dependencies_are_exact_and_scoped`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_direct_dependencies_are_exact_and_scoped`
- [`test_resolver_bootstrap_is_available_before_lock_regeneration`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_resolver_bootstrap_is_available_before_lock_regeneration`
- [`test_resolver_bootstrap_rejects_invalid_source_without_locks`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_resolver_bootstrap_rejects_invalid_source_without_locks`

### `DEP-004` - Jobs install only meaningful tool audiences

**Contract:** Linux quality and exact-lock audit MUST use the dev lock;
compatibility and acceptance MUST use the test lock; distribution construction
MUST use the package lock plus the dev lock's mypy for installed typing smoke;
and Pages MUST use the docs lock. Publication jobs MUST reuse the distribution
artifact and MUST NOT install a build audience or rebuild it.

**Evidence:**

- [`test_ci_preserves_quality_python_package_and_openssh_gates`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_ci_preserves_quality_python_package_and_openssh_gates`

### `DEP-005` - Lock drift and platform wheels are blocking

**Contract:** Lock generation MUST use one exact isolated resolver.
`freeze-check` MUST seed temporary outputs from all four committed locks,
recompile their native inputs without upgrades, and reject any
pin or hash drift. `lock-platform-check` MUST resolve every lock exclusively
from supported CPython 3.13 and 3.14 Linux x86_64 and aarch64 wheels.

**Evidence:**

- [`test_make_exposes_every_governance_boundary`](../../tests/test_project_policy.py) - `tests/test_project_policy.py::test_make_exposes_every_governance_boundary`
- [`test_regenerated_lock_comparison_ignores_only_the_header`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_regenerated_lock_comparison_ignores_only_the_header`

### `DEP-006` - Vulnerability exceptions equal findings exactly

**Contract:** Every lock and every exact resolver-bootstrap package MUST be
audited. The observed package, version, and advisory tuples MUST equal the
reviewed exception set exactly; a new finding, malformed exception, duplicate
exception, or stale exception MUST fail.

**Evidence:**

- [`test_audit_accepts_only_the_exact_reviewed_set`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_audit_accepts_only_the_exact_reviewed_set`
- [`test_live_audit_includes_locks_and_exact_resolver_bootstrap`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_live_audit_includes_locks_and_exact_resolver_bootstrap`

### `DEP-007` - Dependency submission derives all locks offline

**Contract:** The dependency snapshot helper MUST parse exactly the four
committed locks without network access, cross-check direct versions against the
native `.in` owners, reject missing hashes or drift, and emit deterministic
direct/transitive relationships.

**Evidence:**

- [`test_snapshot_is_deterministic_and_contains_every_audience`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_snapshot_is_deterministic_and_contains_every_audience`
- [`test_snapshot_rejects_hashless_and_version_drifted_inputs`](../../tests/test_dependency_governance.py) - `tests/test_dependency_governance.py::test_snapshot_rejects_hashless_and_version_drifted_inputs`

### `DEP-008` - Checkout environments are machine, user, and interpreter scoped

**Contract:** All five persistent Make environments MUST live beneath
`.venvs/<machine-user-key>/<interpreter>/`. The standard-library selector MUST
derive an application-specific hash from a valid nonzero OS machine ID and local
UID, without exposing the raw identity. CPython minors MUST use separate paths.
Missing or invalid identity MUST fail without a shared fallback. Environment
recreation and `make clean` MUST leave legacy environments and other machine,
user, and interpreter environments untouched.
`make venv-path` MUST expose the same selected environment root without requiring
a direct helper invocation or exposing the raw machine identity.

**Evidence:**

- [`test_environment_namespace_is_stable_private_and_scoped`](../../tests/test_machine.py) - `tests/test_machine.py::test_environment_namespace_is_stable_private_and_scoped`
- [`test_invalid_identity_has_no_common_fallback`](../../tests/test_machine.py) - `tests/test_machine.py::test_invalid_identity_has_no_common_fallback`
- [`test_make_scopes_every_environment_and_preserves_other_owners`](../../tests/test_machine.py) - `tests/test_machine.py::test_make_scopes_every_environment_and_preserves_other_owners`
- [`test_make_rejects_failed_namespace_selection`](../../tests/test_machine.py) - `tests/test_machine.py::test_make_rejects_failed_namespace_selection`
- [`test_venv_path_is_exposed_through_make`](../../tests/test_project_policy.py) - `tests/test_project_policy.py::test_venv_path_is_exposed_through_make`
