# Compatibility Contract

## Assertions

### `CMP-001` - CPython 3.13 and 3.14 are the complete Python support range

**Contract:** Package metadata, type-checker configuration, local commands,
documentation, dependency resolution, and CI MUST declare and exercise CPython
3.13 and 3.14. Static analysis MUST target the 3.13 minimum, and runtime source
MUST parse with its grammar. A different minor MUST fail before installation or
testing. Lock generation MAY use the documented 3.14 resolver host, but wheel
resolution MUST cover both supported minors.

**Evidence:**

- [`test_python_and_copyright_ownership_are_exact`](../../tests/test_project_boundary.py) - `tests/test_project_boundary.py::test_python_and_copyright_ownership_are_exact`
- [`test_runtime_sources_parse_with_minimum_supported_grammar`](../../tests/test_project_boundary.py) - `tests/test_project_boundary.py::test_runtime_sources_parse_with_minimum_supported_grammar`
- [`test_public_support_statements_match_package_metadata`](../../tests/test_documentation_contracts.py) - `tests/test_documentation_contracts.py::test_public_support_statements_match_package_metadata`
- [`test_ci_preserves_quality_python_package_and_openssh_gates`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_ci_preserves_quality_python_package_and_openssh_gates`

### `CMP-002` - Every GitHub-hosted job uses Ubuntu 26.04

**Contract:** All repository-owned GitHub-hosted jobs MUST use the exact
`ubuntu-26.04` runner label. The workflow set MUST not mix mutable aliases or
older Ubuntu images into the validation and publication chain.

**Evidence:**

- [`test_every_github_hosted_job_uses_ubuntu_26_04`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_every_github_hosted_job_uses_ubuntu_26_04`

### `CMP-003` - Import and command construction do not require Linux services

**Contract:** Importing the package, validating authorities, constructing
command vectors, and running the ordinary unit suite MUST not require Linux
session services, a live SSH endpoint, or a sibling checkout. This isolation
MUST NOT be presented as support for an undeclared non-Linux runtime platform.

**Evidence:**

- [`test_non_linux_environment_is_a_noop`](../../tests/test_session_environment.py) - `tests/test_session_environment.py::test_non_linux_environment_is_a_noop`
- [`test_runtime_imports_only_standard_library_or_local_modules`](../../tests/test_project_boundary.py) - `tests/test_project_boundary.py::test_runtime_imports_only_standard_library_or_local_modules`

### `CMP-004` - Linux-specific behavior is isolated and accepted with OpenSSH

**Contract:** Linux session recovery MUST degrade to the inherited environment
when its optional probes are unavailable or invalid. CI MUST provision an
OpenSSH server package whose exact Debian version matches the runner's installed
client before real mux and cleanup behavior is tested against an isolated
loopback server.

**Evidence:**

- [`test_ci_preserves_quality_python_package_and_openssh_gates`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_ci_preserves_quality_python_package_and_openssh_gates`
- [`test_missing_probe_executables_are_a_noop`](../../tests/test_session_environment.py) - `tests/test_session_environment.py::test_missing_probe_executables_are_a_noop`
- [`test_real_openssh_one_auth_mux_and_owned_cleanup`](../../tests_acceptance/test_openssh_acceptance.py) - `tests_acceptance/test_openssh_acceptance.py::test_real_openssh_one_auth_mux_and_owned_cleanup`

### `CMP-005` - OpenSSH and remote Python are capability prerequisites

**Contract:** The runtime MUST remain third-party-dependency-free. Consumers
MUST provide a compatible native OpenSSH client; only consumers using
`OwnedRemoteProcess` MUST also provide `python3` on the remote target.

**Evidence:**

- [`test_runtime_imports_only_standard_library_or_local_modules`](../../tests/test_project_boundary.py) - `tests/test_project_boundary.py::test_runtime_imports_only_standard_library_or_local_modules`
- [`test_remote_program_encodes_argv_as_data_once`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_remote_program_encodes_argv_as_data_once`
