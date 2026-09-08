# Public API Contract

## Assertions

### `API-001` - The root module owns the supported import surface

**Contract:** `ssh_wrapper` MUST expose only the documented names in
`ssh_wrapper.__all__`, include `__version__`, and import successfully without a
consumer repository or optional runtime package.

**Evidence:**

- [`test_public_api_and_version_are_owned_by_this_package`](../../tests/test_public_api.py) - `tests/test_public_api.py::test_public_api_and_version_are_owned_by_this_package`
- [`test_public_api_documentation_matches_the_exported_surface`](../../tests/test_public_api.py) - `tests/test_public_api.py::test_public_api_documentation_matches_the_exported_surface`
- [`test_runtime_imports_only_standard_library_or_local_modules`](../../tests/test_project_boundary.py) - `tests/test_project_boundary.py::test_runtime_imports_only_standard_library_or_local_modules`

### `API-002` - Connection authorities are validated structured values

**Contract:** `ConnectionSpec` MUST represent either one validated trusted
OpenSSH alias or validated direct host, user, and port fields. Authority data
MUST remain separate from option and remote-program arguments. IPv6 scope
identifiers MUST NOT admit whitespace, NUL, or shell metacharacters.

**Evidence:**

- [`test_connection_spec_keeps_authority_separate_from_transport`](../../tests/test_connection.py) - `tests/test_connection.py::test_connection_spec_keeps_authority_separate_from_transport`
- [`test_alias_validation_rejects_ambiguous_tokens`](../../tests/test_connection.py) - `tests/test_connection.py::test_alias_validation_rejects_ambiguous_tokens`
- [`test_scoped_ipv6_rejects_unsafe_zone_identifiers`](../../tests/test_connection.py) - `tests/test_connection.py::test_scoped_ipv6_rejects_unsafe_zone_identifiers`

### `API-003` - One master object has a one-way lifecycle

**Contract:** `OpenSSHMaster.start()` MUST be single-use, readiness MUST require
the owned mux, and loss or closure MUST never transition the same object back
to a state that can authenticate again.
Closing during startup MUST prevent a later authentication. Concurrent closure
MUST join the same cleanup; cancellation MUST be propagated only after owned
startup or close resources are reclaimed. An in-flight readiness check MUST NOT
restore READY or LOST after closing.

**Evidence:**

- [`test_master_rejects_readiness_and_a_second_start`](../../tests/test_connection.py) - `tests/test_connection.py::test_master_rejects_readiness_and_a_second_start`
- [`test_lost_master_never_reauthenticates`](../../tests/test_connection.py) - `tests/test_connection.py::test_lost_master_never_reauthenticates`
- [`test_master_close_during_environment_resolution_cannot_authenticate`](../../tests/test_connection.py) - `tests/test_connection.py::test_master_close_during_environment_resolution_cannot_authenticate`
- [`test_cancelled_and_concurrent_master_close_complete_cleanup`](../../tests/test_connection.py) - `tests/test_connection.py::test_cancelled_and_concurrent_master_close_complete_cleanup`
- [`test_closing_during_readiness_cannot_restore_ready_or_lost_state`](../../tests/test_connection.py) - `tests/test_connection.py::test_closing_during_readiness_cannot_restore_ready_or_lost_state`

### `API-004` - Secondary command construction is mux-only

**Contract:** `mux_transport_argv()`, `command_argv()`,
`mux_ssh_command()`, `create_mux_wrapper()`, and `rsync_ssh_command()` MUST bind
to the existing private control socket and MUST prevent authentication or proxy
fallback. Transport forms MUST not embed a destination.

**Evidence:**

- [`test_master_authenticates_once_and_reuses_private_mux`](../../tests/test_connection.py) - `tests/test_connection.py::test_master_authenticates_once_and_reuses_private_mux`
- [`test_direct_transport_and_private_wrapper_never_embed_destination`](../../tests/test_connection.py) - `tests/test_connection.py::test_direct_transport_and_private_wrapper_never_embed_destination`

### `API-005` - Expected failures use one stable error shape

**Contract:** Expected library failures MUST use `SSHError` with a stable code,
human-readable message, and optional structured details. An empty details map
MUST be omitted from `to_dict()`.

**Evidence:**

- [`test_error_without_details_has_the_minimal_stable_shape`](../../tests/test_public_api.py) - `tests/test_public_api.py::test_error_without_details_has_the_minimal_stable_shape`
- [`test_start_failure_is_bounded_path_free_and_cleans_runtime`](../../tests/test_connection.py) - `tests/test_connection.py::test_start_failure_is_bounded_path_free_and_cleans_runtime`
- [`test_runtime_failure_has_stable_path_free_error_and_terminal_state`](../../tests/test_connection.py) - `tests/test_connection.py::test_runtime_failure_has_stable_path_free_error_and_terminal_state`

### `API-006` - Remote process ownership is explicit and observable

**Contract:** `OwnedRemoteProcess` MUST require explicit heartbeat, lease, and
grace timeouts that are positive and finite; the standalone supervisor builder
MUST also reject non-positive or non-finite timeouts. Under the documented
positive `tail_bytes` precondition, it MUST expose
bounded stdout and stderr evidence plus the local mux status; and make repeated
local closure safe. Invalid retention limits MUST fail rather than disable the
bound. Concurrent start attempts MUST NOT spawn multiple supervisors; closing a
pending start MUST prevent later spawning. Cancellation of `close()` MUST finish
owned cleanup before propagating. Cancellation of `wait()` MUST remain observer
cancellation, without implicitly ending a running child's ownership.

**Evidence:**

- [`test_remote_process_rejects_nonpositive_timeouts`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_remote_process_rejects_nonpositive_timeouts`
- [`test_remote_timeouts_reject_nonfinite_values`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_remote_timeouts_reject_nonfinite_values`
- [`test_owner_eof_terminates_only_the_owned_remote_group`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_owner_eof_terminates_only_the_owned_remote_group`
- [`test_remote_start_is_single_use_even_while_readiness_is_pending`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_remote_start_is_single_use_even_while_readiness_is_pending`
- [`test_remote_close_cancels_pending_start_without_spawning`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_remote_close_cancels_pending_start_without_spawning`
- [`test_remote_cancelled_close_still_reaps_child_and_drains`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_remote_cancelled_close_still_reaps_child_and_drains`
- [`test_bounded_storage_rejects_invalid_limits`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_bounded_storage_rejects_invalid_limits`
- [`test_bounded_storage_checks_initial_data_and_mutated_limits`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_bounded_storage_checks_initial_data_and_mutated_limits`
- [`test_cancelling_wait_does_not_release_remote_ownership`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_cancelling_wait_does_not_release_remote_ownership`
- [`test_cancelled_remote_spawn_preserves_time_for_owned_group_cleanup`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_cancelled_remote_spawn_preserves_time_for_owned_group_cleanup`

### `API-007` - Public documentation mirrors the compatibility surface

**Contract:** Public API documentation MUST enumerate every root export,
constructor requirement, compatibility-relevant default, enum value, and
asynchronous lifecycle operation, including bounded-container preconditions.
Documentation MUST NOT advertise an implementation-submodule import as
supported API.

**Evidence:**

- [`test_public_api_documentation_matches_the_exported_surface`](../../tests/test_public_api.py) - `tests/test_public_api.py::test_public_api_documentation_matches_the_exported_surface`
- [`test_public_call_shapes_defaults_and_async_boundaries_are_stable`](../../tests/test_public_api.py) - `tests/test_public_api.py::test_public_call_shapes_defaults_and_async_boundaries_are_stable`
