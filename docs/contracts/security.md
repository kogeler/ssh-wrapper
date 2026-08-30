# Security Contract

## Assertions

### `SEC-001` - One master performs at most one authentication

**Contract:** One `OpenSSHMaster` instance MUST start at most one deliberate
SSH authentication. A second start, readiness loss, or failed master MUST NOT
reconnect or spawn another authentication attempt.

**Evidence:**

- [`test_master_authenticates_once_and_reuses_private_mux`](../../tests/test_connection.py) - `tests/test_connection.py::test_master_authenticates_once_and_reuses_private_mux`
- [`test_lost_master_never_reauthenticates`](../../tests/test_connection.py) - `tests/test_connection.py::test_lost_master_never_reauthenticates`

### `SEC-002` - Secondary channels are mux-only with no fallback

**Contract:** Every secondary channel MUST require the existing private control
socket, disable new authentication methods, set a failing proxy fallback, and
keep authority and remote program values as separate process arguments.

**Evidence:**

- [`test_connection_spec_keeps_authority_separate_from_transport`](../../tests/test_connection.py) - `tests/test_connection.py::test_connection_spec_keeps_authority_separate_from_transport`
- [`test_direct_transport_and_private_wrapper_never_embed_destination`](../../tests/test_connection.py) - `tests/test_connection.py::test_direct_transport_and_private_wrapper_never_embed_destination`

### `SEC-003` - Forwarding and configured commands remain disabled

**Contract:** Initial and secondary SSH invocations MUST disable forwarding,
agent sharing, X11, configured local commands, and configured remote commands.
The private control directory MUST use mode `0700` and cleanup MUST remove only
owned runtime state.

**Evidence:**

- [`test_master_authenticates_once_and_reuses_private_mux`](../../tests/test_connection.py) - `tests/test_connection.py::test_master_authenticates_once_and_reuses_private_mux`
- [`test_control_path_falls_back_to_a_short_owned_runtime`](../../tests/test_connection.py) - `tests/test_connection.py::test_control_path_falls_back_to_a_short_owned_runtime`
- [`test_start_failure_is_bounded_path_free_and_cleans_runtime`](../../tests/test_connection.py) - `tests/test_connection.py::test_start_failure_is_bounded_path_free_and_cleans_runtime`

### `SEC-004` - Session recovery is narrow and initial-only

**Contract:** Linux session recovery MUST probe bounded owned user-session
state, MUST recover only the documented allowlist, MUST preserve inherited
non-empty values, MUST reject invalid runtime directories, and MUST pass the
result only to the initial master subprocess without mutating process state.

**Evidence:**

- [`test_recovers_only_allowlisted_missing_values_with_inherited_precedence`](../../tests/test_session_environment.py) - `tests/test_session_environment.py::test_recovers_only_allowlisted_missing_values_with_inherited_precedence`
- [`test_recovered_environment_is_used_only_for_initial_master`](../../tests/test_connection.py) - `tests/test_connection.py::test_recovered_environment_is_used_only_for_initial_master`

### `SEC-005` - Diagnostics are continuously drained and bounded

**Contract:** Master stderr and supervised child output MUST be drained without
blocking. Master retention MUST use a fixed bound; supervised child retention
MUST remain bounded under the documented positive `tail_bytes` precondition.
Public SSH errors MUST NOT expose raw stderr, executable arguments, identity
files, or private paths.

**Evidence:**

- [`test_ready_master_continuously_drains_bounded_stderr`](../../tests/test_connection.py) - `tests/test_connection.py::test_ready_master_continuously_drains_bounded_stderr`
- [`test_bounded_tail_keeps_only_final_bytes`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_bounded_tail_keeps_only_final_bytes`

### `SEC-006` - Supervision cleans only its owned process group

**Contract:** `OwnedRemoteProcess` MUST encode argv as data, start one new
remote process group, and terminate only that group after owner EOF, malformed
heartbeat, lease expiry, cancellation, or teardown.

**Evidence:**

- [`test_remote_program_encodes_argv_as_data_once`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_remote_program_encodes_argv_as_data_once`
- [`test_owner_eof_terminates_only_the_owned_remote_group`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_owner_eof_terminates_only_the_owned_remote_group`
- [`test_lease_expiry_and_malformed_frame_stop_remote_child`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_lease_expiry_and_malformed_frame_stop_remote_child`

### `SEC-007` - Real OpenSSH acceptance uses isolated ephemeral identity

**Contract:** Linux CI MUST exercise the actual library against an ephemeral
loopback sshd with newly generated keys, isolated configuration and known
hosts, no existing identity or agent, exactly one accepted authentication, one
master connection, mux-only commands, no fallback after loss, bounded output,
and selective owned-group cleanup.

**Evidence:**

- [`test_real_openssh_one_auth_mux_and_owned_cleanup`](../../tests_acceptance/test_openssh_acceptance.py) - `tests_acceptance/test_openssh_acceptance.py::test_real_openssh_one_auth_mux_and_owned_cleanup`
