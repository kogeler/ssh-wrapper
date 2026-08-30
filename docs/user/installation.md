# Installation

## Supported environment

Use CPython 3.13 or 3.14 on Linux with a native OpenSSH client. Package
metadata deliberately rejects Python minors outside that range until they
receive the complete support proof, and its classifiers identify CPython and
Linux as the tested implementation and platform.

Import, authority validation, and command-vector construction do not require a
live SSH endpoint or Linux session services. Starting a master requires the
native client, and interactive-session recovery is Linux-specific.

Install an exact reviewed release with pip:

```bash
python3.13 -m pip install "ssh-wrapper==0.1.0"
```

Replace `python3.13` with `python3.14` when using the other supported minor.

For a virtual environment:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install "ssh-wrapper==0.1.0"
```

The project installs no command-line entry point. `pipx` is therefore not an
appropriate installer for this library.

## Verify the installation

Run this outside a source checkout:

```bash
python3.13 -c 'import ssh_wrapper; print(ssh_wrapper.__version__)'
```

The reported value should equal the version requested from PyPI. Type checkers
discover the bundled `py.typed` marker and the inline annotations without a
separate stub package.

Continue with the [usage guide](usage.md), or review the
[compatibility contract](../contracts/compatibility.md).
