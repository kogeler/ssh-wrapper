# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Container-only entry point: fresh host identity and one unprivileged sshd."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def main() -> None:
    """Use only the supplied public key; never receive a client credential."""
    os.umask(0o077)
    root = Path("/tmp/ssh-wrapper")
    root.mkdir()
    key = os.environ.pop("SSH_WRAPPER_AUTHORIZED_KEY")
    # The host validates the key too; keep this process boundary fail-closed.
    if "\n" in key or "\r" in key or len(key.split()) != 2:
        raise ValueError("expected one public key without options or a comment")
    (root / "authorized_keys").write_text(f"restrict {key}\n", encoding="ascii")
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(root / "host")],
        stdin=subprocess.DEVNULL,
        check=True,
    )
    config = root / "sshd_config"
    config.write_text(
        "\n".join(
            (
                "Port 2222",
                "ListenAddress 0.0.0.0",
                f"HostKey {root}/host",
                f"PidFile {root}/sshd.pid",
                f"AuthorizedKeysFile {root}/authorized_keys",
                "StrictModes yes",
                "UsePAM no",
                "AuthenticationMethods publickey",
                "PubkeyAuthentication yes",
                "PasswordAuthentication no",
                "KbdInteractiveAuthentication no",
                "HostbasedAuthentication no",
                "PermitEmptyPasswords no",
                "PermitRootLogin no",
                "AllowUsers fixture",
                "DisableForwarding yes",
                "PermitUserEnvironment no",
                "LogLevel VERBOSE",
                "Subsystem sftp internal-sftp",
                "",
            )
        ),
        encoding="ascii",
    )
    host_type, host_data, *_comment = (root / "host.pub").read_text().split()
    print(f"SSH_WRAPPER_HOST_KEY {host_type} {host_data}", flush=True)
    os.execv("/usr/sbin/sshd", ["/usr/sbin/sshd", "-D", "-e", "-f", str(config)])


if __name__ == "__main__":
    main()
