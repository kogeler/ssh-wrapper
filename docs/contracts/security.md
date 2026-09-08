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
owned runtime state. Native configuration MUST NOT background owned SSH
processes, enable tunnel forwarding, or discard a mux ownership channel's stdin.
Control path selection MUST reserve space for OpenSSH's 17-byte temporary mux
suffix, and literal percent tokens MUST NOT redirect the owned socket path.

**Evidence:**

- [`test_master_authenticates_once_and_reuses_private_mux`](../../tests/test_connection.py) - `tests/test_connection.py::test_master_authenticates_once_and_reuses_private_mux`
- [`test_control_path_falls_back_to_a_short_owned_runtime`](../../tests/test_connection.py) - `tests/test_connection.py::test_control_path_falls_back_to_a_short_owned_runtime`
- [`test_start_failure_is_bounded_path_free_and_cleans_runtime`](../../tests/test_connection.py) - `tests/test_connection.py::test_start_failure_is_bounded_path_free_and_cleans_runtime`
- [`test_real_openssh_one_auth_mux_and_owned_cleanup`](../../tests_acceptance/test_openssh_acceptance.py) - `tests_acceptance/test_openssh_acceptance.py::test_real_openssh_one_auth_mux_and_owned_cleanup`

### `SEC-004` - Session recovery is narrow and initial-only

**Contract:** Linux session recovery MUST probe bounded owned user-session
state, MUST recover only the documented allowlist, MUST preserve inherited
non-empty values, MUST reject invalid runtime directories, and MUST pass the
result only to the initial master subprocess without mutating process state.
JSON or legacy POSIX-quoted values MUST be decoded only as data; recovered
runtime directories MUST themselves be validated, not only the probe path.
Timeout and cancellation MUST reap owned probe groups even if their leaders
exit before descendants holding output pipes.

**Evidence:**

- [`test_recovers_only_allowlisted_missing_values_with_inherited_precedence`](../../tests/test_session_environment.py) - `tests/test_session_environment.py::test_recovers_only_allowlisted_missing_values_with_inherited_precedence`
- [`test_recovered_environment_is_used_only_for_initial_master`](../../tests/test_connection.py) - `tests/test_connection.py::test_recovered_environment_is_used_only_for_initial_master`
- [`test_session_paths_are_decoded_as_data_without_shell_execution`](../../tests/test_session_environment.py) - `tests/test_session_environment.py::test_session_paths_are_decoded_as_data_without_shell_execution`
- [`test_recovered_runtime_is_validated_not_only_the_probe_runtime`](../../tests/test_session_environment.py) - `tests/test_session_environment.py::test_recovered_runtime_is_validated_not_only_the_probe_runtime`
- [`test_probe_cleanup_kills_descendants_after_the_probe_leader_exits`](../../tests/test_session_environment.py) - `tests/test_session_environment.py::test_probe_cleanup_kills_descendants_after_the_probe_leader_exits`

### `SEC-005` - Diagnostics are continuously drained and bounded

**Contract:** Master stderr and supervised child output MUST be drained without
blocking. Master retention MUST use a fixed bound; supervised child retention
MUST remain bounded under the documented positive `tail_bytes` precondition.
Public SSH errors MUST NOT expose raw stderr, executable arguments, identity
files, or private paths.
Control-operation output MUST also be bounded and continuously drained.
Control checks MUST obey the startup deadline, and cancellation during local
process creation or a control check MUST NOT abandon the subprocess.

**Evidence:**

- [`test_ready_master_continuously_drains_bounded_stderr`](../../tests/test_connection.py) - `tests/test_connection.py::test_ready_master_continuously_drains_bounded_stderr`
- [`test_bounded_tail_keeps_only_final_bytes`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_bounded_tail_keeps_only_final_bytes`
- [`test_control_output_is_bounded_and_fully_drained`](../../tests/test_connection.py) - `tests/test_connection.py::test_control_output_is_bounded_and_fully_drained`
- [`test_startup_deadline_also_bounds_control_checks`](../../tests/test_connection.py) - `tests/test_connection.py::test_startup_deadline_also_bounds_control_checks`
- [`test_control_check_cancellation_reaps_its_process`](../../tests/test_connection.py) - `tests/test_connection.py::test_control_check_cancellation_reaps_its_process`
- [`test_cancellation_during_spawn_recovers_and_reaps_the_handle`](../../tests/test_process_ownership.py) - `tests/test_process_ownership.py::test_cancellation_during_spawn_recovers_and_reaps_the_handle`

### `SEC-006` - Supervision cleans only its owned process group

**Contract:** `OwnedRemoteProcess` MUST encode argv as data, start one new
remote process group, and terminate only that group after owner EOF, malformed
heartbeat, lease expiry, cancelled startup, or teardown. Cleanup MUST include surviving
members even when the group leader exits first or another member ignores SIGTERM.
Natural child exit and termination signals MUST be observed independently of the
heartbeat interval; a completed child MUST NOT wait for the next heartbeat.

**Evidence:**

- [`test_remote_program_encodes_argv_as_data_once`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_remote_program_encodes_argv_as_data_once`
- [`test_owner_eof_terminates_only_the_owned_remote_group`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_owner_eof_terminates_only_the_owned_remote_group`
- [`test_lease_expiry_and_malformed_frame_stop_remote_child`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_lease_expiry_and_malformed_frame_stop_remote_child`
- [`test_supervisor_cleans_descendants_even_after_group_leader_exits`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_supervisor_cleans_descendants_even_after_group_leader_exits`
- [`test_supervisor_observes_child_exit_without_waiting_for_next_heartbeat`](../../tests/test_remote_process.py) - `tests/test_remote_process.py::test_supervisor_observes_child_exit_without_waiting_for_next_heartbeat`

### `SEC-007` - Real OpenSSH acceptance uses isolated ephemeral identity

**Contract:** Linux CI MUST exercise the actual library against an ephemeral
loopback sshd with newly generated keys, isolated configuration and known
hosts, no existing identity or agent, exactly one accepted authentication, one
master connection, mux-only commands, no fallback after loss, bounded output,
and selective owned-group cleanup. The server MUST run as a non-root user in
its own container PID namespace with a read-only root, dropped capabilities,
no-new-privileges and a dynamically assigned port bound only to `127.0.0.1` on
the host. The native client MUST remain on the host; host `sshd` MUST NOT be
required or installed by the gate. The same Make-owned test image and fixture
MUST serve local and CI acceptance. Missing required tools or a failed server
MUST fail the gate, not silently skip it. Container startup, cancellation and
scenario failure MUST reclaim the owned container; remote process checks and
signals MUST execute only inside its PID namespace. PID 1 and orphan reaping
MUST be supplied by the pinned server image. Engine-provided init injection
MUST be disabled, including when enabled in host engine defaults; host
`catatonit`, `tini` or `docker-init` MUST NOT be required by the live gates.
Engine metadata MUST be checked before attempting container creation. Podman
MUST be rootless and use direct per-container `pasta` networking; it MUST NOT
be forced through the shared rootless bridge namespace. Docker MUST retain its
native bridge network. Unknown engine metadata, unavailable pasta, startup and
cleanup failures MUST fail without a fallback network or security relaxation.
The gate MUST NOT change host AppArmor profiles or require `sudo`.

**Evidence:**

- [`test_real_openssh_one_auth_mux_and_owned_cleanup`](../../tests_acceptance/test_openssh_acceptance.py) - `tests_acceptance/test_openssh_acceptance.py::test_real_openssh_one_auth_mux_and_owned_cleanup`
- [`test_failed_server_setup_cleans_only_its_owned_container`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_failed_server_setup_cleans_only_its_owned_container`
- [`test_server_failure_and_remote_checks_stay_in_container_namespace`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_server_failure_and_remote_checks_stay_in_container_namespace`
- [`test_cancellation_during_container_creation_reaps_cli_and_container`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_cancellation_during_container_creation_reaps_cli_and_container`
- [`test_server_rejects_non_loopback_or_invalid_publication`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_server_rejects_non_loopback_or_invalid_publication`
- [`test_missing_client_commands_fail_instead_of_skipping`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_missing_client_commands_fail_instead_of_skipping`
- [`test_server_runs_when_the_engine_has_no_host_init_binary`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_server_runs_when_the_engine_has_no_host_init_binary`
- [`test_server_image_owns_init_instead_of_requesting_host_injection`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_server_image_owns_init_instead_of_requesting_host_injection`
- [`test_live_network_is_selected_from_engine_info`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_live_network_is_selected_from_engine_info`
- [`test_invalid_or_nonrootless_engine_info_fails_before_container_creation`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_invalid_or_nonrootless_engine_info_fails_before_container_creation`
- [`test_engine_info_failure_is_not_retried_with_a_different_network`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_engine_info_failure_is_not_retried_with_a_different_network`
- [`test_podman_pasta_avoids_the_shared_rootless_bridge_cleanup`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_podman_pasta_avoids_the_shared_rootless_bridge_cleanup`
- [`test_container_cleanup_failure_remains_blocking`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_container_cleanup_failure_remains_blocking`

### `SEC-008` - Hardware FIDO acceptance is explicit and operator-assisted

**Contract:** `make test-fido` MUST require an explicitly supplied existing
OpenSSH security-key identity and its public key. It MUST use only a temporary
loopback server, newly generated host key, isolated known hosts and authorization,
and the same one-auth, mux, no-fallback and cleanup checks as automated acceptance.
It MUST NOT generate or modify a hardware credential or request PINs through the
library API. Automatic CI, `make ci`, and `make test-acceptance` MUST NOT select
hardware tests; the operator MUST approve native prompts and touch the key.
Ordinary and FIDO gates MUST reuse one live scenario and the same container
server. Only the selected public authorization key MAY be passed to that
server; client private identities, agent sockets, hardware devices and the
checkout MUST NOT be mounted or copied into the container. Native prompt and
session routing MUST remain available to the host client; D-Bus cleanup MUST
apply only to engine subprocesses.

**Evidence:**

- [`test_real_fido_one_auth_mux_and_owned_cleanup`](../../tests_acceptance/test_fido.py) - `tests_acceptance/test_fido.py::test_real_fido_one_auth_mux_and_owned_cleanup`
- [`test_fido_gate_is_explicit_and_excluded_from_automatic_validation`](../../tests/test_project_policy.py) - `tests/test_project_policy.py::test_fido_gate_is_explicit_and_excluded_from_automatic_validation`
- [`test_server_has_no_host_mounts_devices_or_privileges`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_server_has_no_host_mounts_devices_or_privileges`
- [`test_only_public_key_material_crosses_the_server_boundary`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_only_public_key_material_crosses_the_server_boundary`
- [`test_server_uses_host_buses_but_keeps_client_environment`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_server_uses_host_buses_but_keeps_client_environment`
- [`test_both_gates_reuse_the_live_scenario_without_host_sshd_or_private_key_transfer`](../../tests/test_acceptance_support.py) - `tests/test_acceptance_support.py::test_both_gates_reuse_the_live_scenario_without_host_sshd_or_private_key_transfer`
