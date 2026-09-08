# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Service-independent evidence for the shared live-test container boundary."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests_acceptance import test_openssh_acceptance as live
from tests_acceptance.container_server import ContainerServer, public_authorization

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = "ssh-ed25519 QUJD"
PODMAN_INFO = {"host": {"security": {"rootless": True}}}
DOCKER_INFO = {"OSType": "linux", "ServerVersion": "test"}


@pytest.fixture
def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Execute an inert engine double, not a container or an SSH server."""
    executable = tmp_path / "engine"
    log = tmp_path / "engine.jsonl"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys,time\n"
        "from pathlib import Path\n"
        "argv=sys.argv[1:]\n"
        "debug=argv[:1]==['--log-level=debug']\n"
        "if debug: argv=argv[1:]; print('fixture engine debug',file=sys.stderr)\n"
        "with open(os.environ['ENGINE_LOG'], 'a') as stream:\n"
        " stream.write(json.dumps({'argv':argv,'debug':debug,'pid':os.getpid(),'environment':{\n"
        "  k:os.environ.get(k) for k in ('DBUS_SESSION_BUS_ADDRESS',\n"
        "  'DBUS_SYSTEM_BUS_ADDRESS','XDG_RUNTIME_DIR')}})+'\\n')\n"
        "if argv[0] == os.environ.get('ENGINE_FAIL'):\n"
        " print('fixture engine failure',file=sys.stderr); sys.exit(23)\n"
        "if argv[0] == os.environ.get('ENGINE_HANG'): time.sleep(60)\n"
        "if argv[0] == 'rm' and os.environ.get('ENGINE_BRIDGE_BROKEN') == '1':\n"
        " calls=[json.loads(line)['argv'] for line in Path(os.environ['ENGINE_LOG']).read_text().splitlines()]\n"
        " if any('--network=bridge' in call for call in calls):\n"
        "  print('rootless netns: kill network process: permission denied',file=sys.stderr); sys.exit(125)\n"
        "if argv[0] == 'run' and os.environ.get('ENGINE_NO_INIT') == '1' and '--init=false' not in argv:\n"
        " print('lookup init binary: catatonit is unavailable on the host',file=sys.stderr); sys.exit(125)\n"
        f"if argv[0] == 'info': print(os.environ.get('ENGINE_INFO', {json.dumps(PODMAN_INFO)!r}))\n"
        "elif argv[0] == 'run': print('a'*64)\n"
        "elif argv[0] == 'port': print(os.environ.get('ENGINE_PORT','127.0.0.1:54321'))\n"
        "elif argv[0] == 'logs':\n"
        f" print('SSH_WRAPPER_HOST_KEY {PUBLIC}')\n"
        " print(os.environ.get('ENGINE_READY','Server listening on 0.0.0.0 port 2222.'),file=sys.stderr)\n"
        "elif argv[0] == 'inspect': print('false')\n"
        "elif argv[0] == 'exec': print(123)\n"
        "elif argv[0] == 'build': Path(argv[argv.index('--iidfile')+1]).write_text('sha256:'+'a'*64)\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    monkeypatch.setenv("ENGINE_LOG", str(log))
    monkeypatch.setenv("SSH_WRAPPER_TEST_CONTAINER", str(executable))
    monkeypatch.setenv("SSH_WRAPPER_TEST_IMAGE", "sha256:" + "a" * 64)
    monkeypatch.setenv("SSH_WRAPPER_TEST_DEBUG", "0")
    return log


def records(log: Path) -> list[dict]:
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_container_requires_the_make_prepared_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SSH_WRAPPER_TEST_CONTAINER", raising=False)
    monkeypatch.delenv("SSH_WRAPPER_TEST_IMAGE", raising=False)
    with pytest.raises(RuntimeError, match="make test-acceptance or make test-fido"):
        ContainerServer(PUBLIC)


@pytest.mark.parametrize(
    "key",
    (
        "",
        'command="true" sk-ssh-ed25519@openssh.com QUJD',
        PUBLIC,
        "sk-ssh-ed25519@openssh.com ***",
        "sk-ssh-ed25519@openssh.com QUJD\nsecond key",
    ),
)
def test_fido_authorization_rejects_invalid_or_nonhardware_keys(key: str) -> None:
    with pytest.raises(ValueError):
        public_authorization(key, fido=True)


@pytest.mark.parametrize(
    "key_type", ("sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com")
)
def test_only_public_key_material_crosses_the_server_boundary(key_type: str) -> None:
    assert (
        public_authorization(f"{key_type} QUJD private/path and comment\n", fido=True)
        == f"{key_type} QUJD"
    )


@pytest.mark.parametrize("network", ("pasta", "bridge"))
def test_server_has_no_host_mounts_devices_or_privileges(
    engine: Path, network: str
) -> None:
    server = ContainerServer(PUBLIC)
    argv = server.run_argv(network)
    assert {
        "--init=false",
        "--read-only",
        "--cap-drop=all",
        "--user=10000:10000",
        "--security-opt=no-new-privileges",
        f"--network={network}",
        "--publish=127.0.0.1::2222",
        "--pull=never",
    }.issubset(argv)
    assert not any(
        value.startswith(
            (
                "--volume",
                "--mount",
                "--device",
                "--privileged",
                "--pid=host",
                "--network=host",
                "--cgroup",
                "--events-backend",
                "--security-opt=apparmor=",
                "--security-opt=seccomp=",
            )
        )
        for value in argv
    )
    assert argv[argv.index("--env") + 1] == f"SSH_WRAPPER_AUTHORIZED_KEY={PUBLIC}"
    assert argv[-1] == os.environ["SSH_WRAPPER_TEST_IMAGE"]
    assert str(ROOT) not in " ".join(argv)


@pytest.mark.parametrize(
    "info,network", ((PODMAN_INFO, "pasta"), (DOCKER_INFO, "bridge"))
)
async def test_live_network_is_selected_from_engine_info(
    engine: Path, monkeypatch: pytest.MonkeyPatch, info: dict, network: str
) -> None:
    monkeypatch.setenv("ENGINE_INFO", json.dumps(info))
    async with ContainerServer(PUBLIC):
        commands = [call["argv"] for call in records(engine)]
        assert commands[0] == ["info", "--format", "{{json .}}"]
        runs = [command for command in commands if command[0] == "run"]
        assert len(runs) == 1
        assert [arg for arg in runs[0] if arg.startswith("--network=")] == [
            f"--network={network}"
        ]
        assert "--publish=127.0.0.1::2222" in runs[0]


@pytest.mark.parametrize(
    "info",
    (
        "not json",
        "[]",
        "{}",
        '{"host": null}',
        '{"host": {"security": {"rootless": false}}}',
        '{"host": {"security": {"rootless": "true"}}}',
        '{"host": {"security": {}}}',
        '{"OSType": "windows", "ServerVersion": "test"}',
    ),
)
async def test_invalid_or_nonrootless_engine_info_fails_before_container_creation(
    engine: Path, monkeypatch: pytest.MonkeyPatch, info: str
) -> None:
    monkeypatch.setenv("ENGINE_INFO", info)
    with pytest.raises(RuntimeError, match="container engine info|requires rootless"):
        async with ContainerServer(PUBLIC):
            pytest.fail("invalid engine info reached the client")
    assert [call["argv"][0] for call in records(engine)] == ["info"]


async def test_engine_info_failure_is_not_retried_with_a_different_network(
    engine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENGINE_FAIL", "info")
    with pytest.raises(RuntimeError, match="fixture engine failure"):
        async with ContainerServer(PUBLIC):
            pytest.fail("failed engine info reached the client")
    assert [call["argv"][0] for call in records(engine)] == ["info"]


async def test_podman_pasta_avoids_the_shared_rootless_bridge_cleanup(
    engine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENGINE_BRIDGE_BROKEN", "1")
    async with ContainerServer(PUBLIC) as server:
        assert server.port == 54321
    commands = [call["argv"] for call in records(engine)]
    assert "--network=pasta" in commands[1]
    assert not any("--network=bridge" in command for command in commands)
    assert commands[-1] == ["rm", "--force", server.name]


async def test_container_cleanup_failure_remains_blocking(
    engine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENGINE_FAIL", "rm")
    with pytest.raises(RuntimeError, match="container rm failed"):
        async with ContainerServer(PUBLIC):
            pass
    commands = [call["argv"][0] for call in records(engine)]
    assert commands.count("run") == commands.count("rm") == 1


@pytest.mark.parametrize("debug", ("0", "1"))
async def test_make_debug_option_changes_only_engine_logging(
    engine: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    debug: str,
) -> None:
    monkeypatch.setenv("SSH_WRAPPER_TEST_DEBUG", debug)
    async with ContainerServer(PUBLIC):
        pass
    assert all(call["debug"] == (debug == "1") for call in records(engine))
    assert ("fixture engine debug" in capsys.readouterr().err) == (debug == "1")
    runs = [call["argv"] for call in records(engine) if call["argv"][0] == "run"]
    assert len(runs) == 1 and "--network=pasta" in runs[0]


def test_invalid_debug_option_fails_without_an_engine_call(
    engine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SSH_WRAPPER_TEST_DEBUG", "unexpected")
    with pytest.raises(ValueError, match="must be 0 or 1"):
        ContainerServer(PUBLIC)
    assert not engine.exists()


async def test_server_runs_when_the_engine_has_no_host_init_binary(
    engine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENGINE_NO_INIT", "1")
    async with ContainerServer(PUBLIC) as server:
        assert server.port == 54321
    assert records(engine)[-1]["argv"] == ["rm", "--force", server.name]


def test_server_image_owns_init_instead_of_requesting_host_injection(
    engine: Path,
) -> None:
    argv = ContainerServer(PUBLIC).run_argv("pasta")
    assert [argument for argument in argv if argument.startswith("--init")] == [
        "--init=false"
    ]
    containerfile = (ROOT / "tests_acceptance/server/Containerfile").read_text()
    assert re.search(
        r"apt-get install[^\n]*\bopenssh-server\b[^\n]*\btini\b", containerfile
    )
    entrypoint = re.search(r"^ENTRYPOINT (.+)$", containerfile, re.MULTILINE)
    assert entrypoint is not None
    assert json.loads(entrypoint[1]) == [
        "/usr/bin/tini",
        "--",
        "python3",
        "/opt/ssh-wrapper/server.py",
    ]


async def test_server_uses_host_buses_but_keeps_client_environment(
    engine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/private/session")
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", "unix:path=/private/system")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/owned/runtime")
    async with ContainerServer(PUBLIC) as server:
        assert server.port == 54321 and server.host_key == PUBLIC
        assert "Server listening" in await server.logs()
        assert os.environ["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/private/session"
    for call in records(engine):
        assert call["environment"] == {
            "DBUS_SESSION_BUS_ADDRESS": None,
            "DBUS_SYSTEM_BUS_ADDRESS": None,
            "XDG_RUNTIME_DIR": "/owned/runtime",
        }
    assert records(engine)[-1]["argv"] == ["rm", "--force", server.name]
    commands = [call["argv"] for call in records(engine)]
    assert sum(command[0] == "run" for command in commands) == 1
    assert "--network=pasta" in commands[1]


@pytest.mark.parametrize("failure", ("run", "port", "logs"))
async def test_failed_server_setup_cleans_only_its_owned_container(
    engine: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    monkeypatch.setenv("ENGINE_FAIL", failure)
    server = ContainerServer(PUBLIC)
    with pytest.raises(RuntimeError, match="fixture engine failure"):
        async with server:
            pytest.fail("failed setup reached the client")
    assert records(engine)[-1]["argv"] == ["rm", "--force", server.name]
    runs = [call["argv"] for call in records(engine) if call["argv"][0] == "run"]
    assert len(runs) == 1 and "--network=pasta" in runs[0]


@pytest.mark.parametrize(
    "published",
    ("0.0.0.0:54321", "[::]:54321", "127.0.0.1:0", "127.0.0.1:54321\n0.0.0.0:54321"),
)
async def test_server_rejects_non_loopback_or_invalid_publication(
    engine: Path, monkeypatch: pytest.MonkeyPatch, published: str
) -> None:
    monkeypatch.setenv("ENGINE_PORT", published)
    server = ContainerServer(PUBLIC)
    with pytest.raises(RuntimeError, match="exclusively to loopback"):
        async with server:
            pytest.fail("unsafe binding reached the client")
    assert records(engine)[-1]["argv"] == ["rm", "--force", server.name]


async def test_server_failure_and_remote_checks_stay_in_container_namespace(
    engine: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: object) -> None:
        pytest.fail("a container PID reached a host process operation")

    monkeypatch.setattr(os, "kill", forbidden)
    monkeypatch.setattr(os, "getpgid", forbidden)
    server = ContainerServer(PUBLIC)
    with pytest.raises(AssertionError, match="scenario failed"):
        async with server:
            pid = await server.wait_for_pid_file(server.directory / "owned.pid")
            assert pid == await server.process_group(pid) == 123
            await server.signal(pid, 0)
            await server.wait_for_pid_exit(pid)
            with pytest.raises(ValueError, match="container init"):
                await server.signal(1, 15)
            raise AssertionError("scenario failed")
    commands = [call["argv"] for call in records(engine)]
    assert sum(command[0] == "exec" for command in commands) == 4
    assert all(
        command[1:4] == [server.name, "python3", "-c"]
        for command in commands
        if command[0] == "exec"
    )
    assert commands[-1] == ["rm", "--force", server.name]


@pytest.mark.parametrize("operation", ("info", "run"))
async def test_cancellation_during_container_creation_reaps_cli_and_container(
    engine: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    monkeypatch.setenv("ENGINE_HANG", operation)
    server = ContainerServer(PUBLIC)
    task = asyncio.create_task(server.__aenter__())
    async with asyncio.timeout(5):
        while (
            not engine.exists()
            or not (calls := records(engine))
            or calls[-1]["argv"][0] != operation
        ):
            await asyncio.sleep(0.01)
    pid = calls[-1]["pid"]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    if operation == "run":
        assert records(engine)[-1]["argv"] == ["rm", "--force", server.name]
    else:
        assert [call["argv"][0] for call in records(engine)] == ["info"]


def test_missing_client_commands_fail_instead_of_skipping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(
        pytest.fail.Exception, match="client command is unavailable: ssh"
    ):
        live._program("ssh")


def test_make_and_ci_share_the_pinned_server_without_host_sshd() -> None:
    makefile = (ROOT / "Makefile").read_text()
    for name in ("test-fido", "test-acceptance"):
        recipe = re.search(rf"^{name}:.*?(?=\n\S)", makefile, re.MULTILINE | re.DOTALL)
        assert recipe is not None and "venv-test acceptance-image" in recipe.group()
        assert 'SSH_WRAPPER_TEST_CONTAINER="$(CONTAINER)"' in recipe.group()
        assert "SSH_WRAPPER_TEST_IMAGE=" in recipe.group()
        assert 'SSH_WRAPPER_TEST_DEBUG="$(ACCEPTANCE_DEBUG)"' in recipe.group()
    ci = re.search(r"^ci: (.+)$", makefile, re.MULTILINE)
    assert ci is not None and ci[1].split().count("test-acceptance") == 1
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "openssh-server=" not in workflow and "command -v sshd" not in workflow
    containerfile = (ROOT / "tests_acceptance/server/Containerfile").read_text()
    assert re.search(r"^FROM [^\s]+@sha256:[0-9a-f]{64}$", containerfile, re.MULTILINE)
    assert "snapshot.debian.org/archive/debian/" in containerfile
    assert "snapshot.debian.org/archive/debian-security/" in containerfile
    assert "USER 10000:10000" in containerfile


@pytest.mark.parametrize("fido", (False, True))
async def test_both_gates_reuse_the_live_scenario_without_host_sshd_or_private_key_transfer(
    engine: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fido: bool
) -> None:
    identity = tmp_path / "hardware identity"
    identity.write_text("PRIVATE MATERIAL MUST STAY ON THE HOST", encoding="ascii")
    Path(f"{identity}.pub").write_text(
        "sk-ssh-ed25519@openssh.com QUJD secret/path comment\n", encoding="ascii"
    )
    requested: list[str] = []
    generated: list[Path] = []
    exercised: list[bool] = []

    def program(name: str) -> Path:
        assert name in {"ssh", "ssh-keygen", "false"}
        requested.append(name)
        return Path("/fake") / name

    def generate_key(_keygen: Path, destination: Path) -> None:
        generated.append(destination)
        destination.write_text("ephemeral client", encoding="ascii")
        Path(f"{destination}.pub").write_text(PUBLIC, encoding="ascii")

    read_text = Path.read_text

    def reject_private_reads(path: Path, *args: object, **kwargs: object) -> str:
        assert path.resolve() != identity, (
            "a private hardware identity was read by the harness"
        )
        return read_text(path, *args, **kwargs)

    async def exercise_client(
        root: Path, server: ContainerServer, **options: object
    ) -> None:
        assert root == tmp_path and server.host_key == PUBLIC
        assert options["fido"] is fido
        if fido:
            assert options["client_key"].is_symlink()
            assert options["client_key"].resolve() == identity
        exercised.append(fido)

    monkeypatch.setattr(live, "_program", program)
    monkeypatch.setattr(live, "_generate_key", generate_key)
    monkeypatch.setattr(live, "_exercise_client", exercise_client)
    monkeypatch.setattr(Path, "read_text", reject_private_reads)
    await live._exercise_openssh(
        tmp_path, monkeypatch, fido_identity=identity if fido else None
    )
    assert exercised == [fido]
    assert len(generated) == (0 if fido else 1)
    assert requested == (["ssh", "false"] if fido else ["ssh", "false", "ssh-keygen"])
    argv = next(call["argv"] for call in records(engine) if call["argv"][0] == "run")
    authorization = argv[argv.index("--env") + 1]
    assert authorization == "SSH_WRAPPER_AUTHORIZED_KEY=" + (
        "sk-ssh-ed25519@openssh.com QUJD" if fido else PUBLIC
    )
    assert str(identity) not in " ".join(argv)


@pytest.mark.parametrize("status", (0, 23))
def test_make_server_build_sanitizes_only_engine_buses_and_propagates_failure(
    engine: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    shutil.copy2(ROOT / "Makefile", tmp_path / "Makefile")
    (tmp_path / "tools").mkdir()
    shutil.copy2(ROOT / "tools/machine.py", tmp_path / "tools/machine.py")
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/private/session")
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", "unix:path=/private/system")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/owned/runtime")
    if status:
        monkeypatch.setenv("ENGINE_FAIL", "build")
    environment = dict(os.environ)
    for name in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES"):
        environment.pop(name, None)
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "acceptance-image",
            f"PY={sys.executable}",
            f"CONTAINER={environment['SSH_WRAPPER_TEST_CONTAINER']}",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode == 0) == (status == 0), result.stderr
    call = records(engine)[0]
    assert call["environment"] == {
        "DBUS_SESSION_BUS_ADDRESS": None,
        "DBUS_SYSTEM_BUS_ADDRESS": None,
        "XDG_RUNTIME_DIR": "/owned/runtime",
    }
    assert call["argv"][:3] == [
        "build",
        "--file",
        "tests_acceptance/server/Containerfile",
    ]
    assert call["argv"][-1] == "tests_acceptance/server"
    assert not any(
        arg.startswith(("--cgroup", "--events-backend")) for arg in call["argv"]
    )
