# Continuous Integration And Release Contract

## Assertions

### `CIR-001` - Workflow topology is event-driven and immutable

**Contract:** The repository MUST contain only CI, dependency submission,
Pages, PR-body, and release workflows. Every GitHub-hosted job MUST run on
`ubuntu-26.04`; external actions MUST use full commit SHAs; validator images
MUST use immutable digests; checkout credentials MUST not persist; and every
workflow MUST declare permissions and concurrency.

**Evidence:**

- [`test_workflow_set_is_event_driven_and_every_action_is_sha_pinned`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_workflow_set_is_event_driven_and_every_action_is_sha_pinned`
- [`test_every_github_hosted_job_uses_ubuntu_26_04`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_every_github_hosted_job_uses_ubuntu_26_04`

### `CIR-002` - Quality, compatibility, package, and OpenSSH remain visible gates

**Contract:** Reusable CI MUST assign source/policy, compatibility/coverage,
distribution, hermetic OpenSSH, dependency review with an every-event exact-lock
audit, Python and Actions CodeQL, and version progression to visible scoped
jobs. Compatibility MUST run once for each declared Python minor; every other
expensive gate MUST run once per invocation. No umbrella job MAY repeat another
job's tests or build.

**Evidence:**

- [`test_ci_preserves_quality_python_package_and_openssh_gates`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_ci_preserves_quality_python_package_and_openssh_gates`

### `CIR-003` - Write permissions are job-scoped

**Contract:** Default workflow permission MUST be read-only contents. Only
CodeQL MAY write security events, dependency submission MAY write contents,
Pages deploy MAY write Pages and OIDC, PR-body automation MAY write pull
requests, PyPI publication MAY write OIDC, and final GitHub publication MAY
write contents. Each exception MUST be confined to its owning job.

**Evidence:**

- [`test_workflow_write_permissions_are_confined`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_workflow_write_permissions_are_confined`

### `CIR-004` - PR-body automation treats head content as bounded data

**Contract:** PR-body automation MUST be the only `pull_request_target`
boundary, run only for pull requests that change `CHANGELOG.md`, execute only
trusted default-branch code, read a bounded head changelog through the API as
inert data, preserve manual body text, and refuse concurrent overwrite. It MUST
select the newest populated level-two section, including `Unreleased` without
a version change, and reject malformed or reserved managed markers.

**Evidence:**

- [`test_pr_body_is_only_pull_request_target_boundary`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_pr_body_is_only_pull_request_target_boundary`
- [`test_pr_body_preserves_manual_text_and_replaces_only_managed_content`](../../tests/test_release_helpers.py) - `tests/test_release_helpers.py::test_pr_body_preserves_manual_text_and_replaces_only_managed_content`
- [`test_pr_body_prefers_populated_unreleased_without_a_version_change`](../../tests/test_release_helpers.py) - `tests/test_release_helpers.py::test_pr_body_prefers_populated_unreleased_without_a_version_change`
- [`test_pr_body_rejects_malformed_markers_and_empty_notes`](../../tests/test_release_helpers.py) - `tests/test_release_helpers.py::test_pr_body_rejects_malformed_markers_and_empty_notes`

### `CIR-005` - Version progression compares exact base and head

**Contract:** Pull requests and later main pushes MUST compare the exact base
and proposed `.version` values. The first repository commit MAY compare against
`0.0.0`. Ordinary maintenance MAY retain an already published stable version
while `Unreleased` accumulates. A changed version MUST advance beyond the exact
base. Same-version unpublished recovery MUST advance beyond the latest stable
release; drafts and prereleases MUST NOT count as published stable versions.

**Evidence:**

- [`test_version_job_compares_exact_base_and_head`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_version_job_compares_exact_base_and_head`
- [`test_unpublished_recovery_and_exact_notes`](../../tests/test_release_governance.py) - `tests/test_release_governance.py::test_unpublished_recovery_and_exact_notes`
- [`test_ci_only_treats_stable_published_versions_as_maintenance`](../../tests/test_release_workflow.py) - `tests/test_release_workflow.py::test_ci_only_treats_stable_published_versions_as_maintenance`
- [`test_ci_passes_version_checks_the_exact_progression_arguments`](../../tests/test_release_workflow.py) - `tests/test_release_workflow.py::test_ci_passes_version_checks_the_exact_progression_arguments`

### `CIR-006` - Publication builds once and never replaces conflict

**Contract:** Reusable CI's distribution job MUST build and smoke the
wheel/sdist once and, for the trusted release caller only, upload that exact
pair as one immutable workflow artifact. No other maintained workflow MAY set
that upload input. Release jobs MUST consume it without any rebuild for PyPI
and GitHub. Published or draft tags, targets, notes, metadata, asset names,
sizes, and hashes MUST be verified; conflict MUST fail without moving tags,
deleting assets, or overwriting files.

Every direct-main push MUST first inspect both publication targets. An exact
complete published release MUST skip reusable release CI and both publication
jobs, even when main has advanced. Published version, notes, and target metadata
MUST be validated against the immutable tagged source; draft recovery MUST
remain tied to the current release commit. Missing tags and incomplete or
conflicting publication state MUST fail closed.

**Evidence:**

- [`test_release_reuses_ci_and_shared_python_distributions`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_release_reuses_ci_and_shared_python_distributions`
- [`test_release_state_is_exact_and_recovery_is_non_destructive`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_release_state_is_exact_and_recovery_is_non_destructive`
- [`test_published_release_uses_tagged_source_and_needs_no_work`](../../tests/test_release_workflow.py) - `tests/test_release_workflow.py::test_published_release_uses_tagged_source_and_needs_no_work`
- [`test_unfinished_publication_requires_ci_and_only_missing_targets`](../../tests/test_release_workflow.py) - `tests/test_release_workflow.py::test_unfinished_publication_requires_ci_and_only_missing_targets`
- [`test_publication_conflicts_fail_before_enabling_release`](../../tests/test_release_workflow.py) - `tests/test_release_workflow.py::test_publication_conflicts_fail_before_enabling_release`

### `CIR-007` - Dependency submission is trusted-main-only

**Contract:** Dependency submission MUST trigger only on direct `main` pushes
that change dependency ownership, a lock, or snapshot automation; derive and
validate all four manifests offline; verify the expected repository and payload
shape; and use only its job-scoped standard token and contents write.

**Evidence:**

- [`test_dependency_submission_is_trusted_main_only`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_dependency_submission_is_trusted_main_only`

### `CIR-008` - Documentation changes build before merge and deploy from main

**Contract:** Documentation and docs-tool changes MUST trigger a strict
non-deploying Pages build on pull requests. Direct `main` builds MUST audit
routes, links, anchors, assets, canonical URLs, sitemap XML/gzip, robots, root
files, and the absence of insecure HTTP references before a deploy job receives
Pages and OIDC writes.

**Evidence:**

- [`test_pages_validates_prs_and_confines_publish_permissions`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_pages_validates_prs_and_confines_publish_permissions`
- [`test_generated_site_audit_accepts_complete_project_site`](../../tests/test_docs_site_audit.py) - `tests/test_docs_site_audit.py::test_generated_site_audit_accepts_complete_project_site`

### `CIR-009` - Contract evidence is machine-checked

**Contract:** Contract files MUST be the only normative documentation, MUST use
unique sequential IDs, and MUST link every assertion to at least one existing
test definition. User, maintenance, and site-only inputs MUST remain separate,
and every relative documentation link MUST resolve.

**Evidence:**

- [`test_contract_assertions_have_unique_ids_and_real_evidence`](../../tests/test_documentation_contracts.py) - `tests/test_documentation_contracts.py::test_contract_assertions_have_unique_ids_and_real_evidence`
- [`test_documentation_tree_navigation_and_language_are_separated`](../../tests/test_documentation_contracts.py) - `tests/test_documentation_contracts.py::test_documentation_tree_navigation_and_language_are_separated`
- [`test_public_python_examples_compile_and_import_only_root_api`](../../tests/test_documentation_contracts.py) - `tests/test_documentation_contracts.py::test_public_python_examples_compile_and_import_only_root_api`

### `CIR-010` - Repository ownership is explicit

**Contract:** CODEOWNERS MUST assign every repository path to `@kogeler`, so a
default-branch ruleset can require code-owner review for every change.

**Evidence:**

- [`test_codeowners_assigns_entire_repository_to_kogeler`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_codeowners_assigns_entire_repository_to_kogeler`

### `CIR-011` - PyPI publication is secretless, exact, and recoverable

**Contract:** Release state MUST inspect PyPI and GitHub independently. A
missing PyPI version MUST publish only the gated wheel/sdist through the `pypi`
Environment, PyPI Trusted Publishing, a job-scoped OIDC token, and the pinned
official PyPA action. Stored credentials and blind duplicate skipping MUST be
absent. Existing PyPI files MUST match local names, types, sizes, hashes, and
yanked state before GitHub recovery continues.

**Evidence:**

- [`test_pypi_publication_uses_oidc_without_stored_credentials`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_pypi_publication_uses_oidc_without_stored_credentials`
- [`test_pypi_verifier_accepts_only_exact_local_files`](../../tests/test_release_helpers.py) - `tests/test_release_helpers.py::test_pypi_verifier_accepts_only_exact_local_files`

### `CIR-012` - Mutable pins have executable owners

**Contract:** Project versions, dependency pins, action commits, image digests,
runner labels, and release conventions MUST be owned by the executable
configuration that consumes them. Tests MUST verify structure and relationships
without duplicating unrelated mutable literals.

**Evidence:**

- [`test_mutable_pins_have_executable_owners`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_mutable_pins_have_executable_owners`

### `CIR-013` - Automation is scoped to a Python library

**Contract:** CI and release automation MUST build distributable products only
as the standard pure Python wheel and source distribution. It MUST NOT contain standalone
application, native executable, application-container, Node application, or Rust
build processes. A local test-only SSH server image MAY be built by the owning
acceptance Make target, MUST NOT be published, and MUST remain outside Python
distributions. Quality, tests, distributions, and OpenSSH acceptance MUST each
have one workflow owner, and publication MUST not rebuild CI artifacts.

**Evidence:**

- [`test_ci_has_one_owner_per_library_gate_and_no_application_builds`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_ci_has_one_owner_per_library_gate_and_no_application_builds`

### `CIR-014` - Local and CI container validation share one Make boundary

**Contract:** Local and hosted workflow validation MUST invoke the same
`make validate-actions` contract, also included by `make policy` and `make ci`.
The container engine subprocess MUST receive neither `DBUS_SESSION_BUS_ADDRESS`
nor `DBUS_SYSTEM_BUS_ADDRESS` from the caller, so private application buses
cannot redirect access to host services. `XDG_RUNTIME_DIR` and the caller's
environment MUST remain intact. Native cgroup and event backends MUST NOT be
replaced to mask a failure. The target MUST retain its immutable image,
network isolation, read-only root and repository mount, dropped capabilities,
and no-new-privileges policy, and MUST propagate engine failure without retrying
under weaker settings. Ad-hoc engine overrides and direct tool commands MUST
NOT substitute for passing the maintained Make targets.
The acceptance image build and all acceptance engine operations MUST apply
the same D-Bus-only environment cleanup without altering native client prompt
routing or selecting alternate engine backends. Both live gates MUST prepare
their server through `make acceptance-image`; `make ci` MUST include ordinary
container-backed acceptance exactly once and MUST exclude hardware interaction.
Live networking MUST be selected from engine metadata by the shared fixture:
direct `pasta` for rootless Podman, native bridge for Docker. This selection
MUST NOT depend on whether the caller is CI or local, or on the engine's
executable filename. No network or AppArmor fallback MAY mask teardown errors.
The optional Make setting `ACCEPTANCE_DEBUG=1` MAY add engine debug logging and
bounded stderr output only; it MUST NOT alter network or security arguments.

**Evidence:**

- [`test_container_validation_uses_host_buses_and_propagates_failure`](../../tests/test_project_policy.py) - `tests/test_project_policy.py::test_container_validation_uses_host_buses_and_propagates_failure`
- [`test_make_exposes_every_governance_boundary`](../../tests/test_project_policy.py) - `tests/test_project_policy.py::test_make_exposes_every_governance_boundary`
- [`test_ci_preserves_quality_python_package_and_openssh_gates`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_ci_preserves_quality_python_package_and_openssh_gates`
- [`test_make_server_build_sanitizes_only_engine_buses_and_propagates_failure`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_make_server_build_sanitizes_only_engine_buses_and_propagates_failure`
- [`test_make_and_ci_share_the_pinned_server_without_host_sshd`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_make_and_ci_share_the_pinned_server_without_host_sshd`
- [`test_live_network_is_selected_from_engine_info`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_live_network_is_selected_from_engine_info`
- [`test_podman_pasta_avoids_the_shared_rootless_bridge_cleanup`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_podman_pasta_avoids_the_shared_rootless_bridge_cleanup`
- [`test_make_debug_option_changes_only_engine_logging`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_make_debug_option_changes_only_engine_logging`
- [`test_invalid_debug_option_fails_without_an_engine_call`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_invalid_debug_option_fails_without_an_engine_call`
