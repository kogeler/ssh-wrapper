# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Verify exact release archive inventories, metadata, and normalized bytes."""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import hashlib
import io
import os
import struct
import sys
import tarfile
import tomllib
import zipfile
from email import policy
from email.message import Message
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

if __package__:
    from .checksums import verify as verify_checksums
    from .dependency_policy import PolicyError, read_input
else:
    from checksums import verify as verify_checksums
    from dependency_policy import PolicyError, read_input

ROOT = Path(__file__).resolve().parents[1]
MODULES = {
    "__init__.py",
    "_process.py",
    "bounded.py",
    "connection.py",
    "errors.py",
    "py.typed",
    "remote_process.py",
    "session_environment.py",
}
PROJECT_URLS = {
    "Homepage, https://kogeler.github.io/ssh-wrapper/",
    "Documentation, https://kogeler.github.io/ssh-wrapper/",
    "Repository, https://github.com/kogeler/ssh-wrapper",
    "Issues, https://github.com/kogeler/ssh-wrapper/issues",
    "Changelog, https://github.com/kogeler/ssh-wrapper/blob/main/CHANGELOG.md",
}
FORBIDDEN_BYTES = (
    b"remote-ssh-mcp-server",
    b"remote_ssh_mcp",
    b"remote_xpra",
    b"joplin-md-sync",
    b"joplin_md_sync",
)


class DistributionError(ValueError):
    """A built archive violates the public distribution contract."""


def safe_parts(name: str) -> tuple[str, ...]:
    """Return safe relative POSIX path parts."""
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise DistributionError(f"unsafe archive member: {name}")
    return path.parts


def _metadata(
    data: bytes, *, version: str, readme: str, project: dict[str, object]
) -> Message:
    message = BytesParser(policy=policy.default).parsebytes(data)
    expected = {
        "Metadata-Version": "2.4",
        "Name": "ssh-wrapper",
        "Version": version,
        "Summary": "One-auth OpenSSH ControlMaster lifecycle with mux-only channels",
        "Author": "kogeler",
        "Maintainer": "kogeler",
        "License-Expression": "MIT",
        "Requires-Python": "<3.15,>=3.13",
        "Description-Content-Type": "text/markdown",
        "License-File": "LICENSE",
    }
    for key, value in expected.items():
        if message.get(key) != value:
            raise DistributionError(
                f"metadata {key}={message.get(key)!r}, expected {value!r}"
            )
    if set(message.get_all("Project-URL", [])) != PROJECT_URLS:
        raise DistributionError("metadata project URLs differ from the public routes")
    keywords = project.get("keywords")
    if not isinstance(keywords, list) or not all(
        isinstance(keyword, str) for keyword in keywords
    ):
        raise DistributionError("source project keywords are invalid")
    if message.get("Keywords") != ",".join(keywords):
        raise DistributionError("metadata keywords differ from pyproject.toml")
    classifiers = project.get("classifiers")
    if not isinstance(classifiers, list) or not all(
        isinstance(classifier, str) for classifier in classifiers
    ):
        raise DistributionError("source project classifiers are invalid")
    if message.get_all("Classifier", []) != classifiers:
        raise DistributionError("metadata classifiers differ from pyproject.toml")
    if project.get("dependencies") != [] or "optional-dependencies" in project:
        raise DistributionError(
            "source metadata must have no runtime or maintainer dependencies"
        )
    if message.get_all("Requires-Dist", []) or message.get_all("Provides-Extra", []):
        raise DistributionError(
            "metadata must not publish runtime dependencies or maintainer extras"
        )
    if message.get_all("Dynamic", []) != ["license-file"]:
        raise DistributionError("metadata dynamic field inventory differs")
    payload = message.get_payload()
    if not isinstance(payload, str) or payload.strip() != readme.strip():
        raise DistributionError("metadata long description differs from README.md")
    return message


def _forbidden(data: bytes, *, root: Path, source: str) -> None:
    patterns = (*FORBIDDEN_BYTES, os.fsencode(root.resolve()))
    for pattern in patterns:
        if pattern and pattern in data:
            raise DistributionError(f"private or foreign marker appears in {source}")


def verify_wheel(path: Path, *, root: Path, version: str, epoch: int) -> None:
    """Verify the pure wheel, metadata, PEP 561 marker, and RECORD."""
    dist_info = f"ssh_wrapper-{version}.dist-info"
    expected_files = {
        *(f"ssh_wrapper/{name}" for name in MODULES),
        f"{dist_info}/METADATA",
        f"{dist_info}/WHEEL",
        f"{dist_info}/top_level.txt",
        f"{dist_info}/RECORD",
        f"{dist_info}/licenses/LICENSE",
    }
    expected_timestamp = dt.datetime.fromtimestamp(
        epoch - (epoch % 2), tz=dt.UTC
    ).timetuple()[:6]
    with zipfile.ZipFile(path) as archive:
        items = archive.infolist()
        names = [item.filename for item in items]
        if len(names) != len(set(names)) or names != sorted(names):
            raise DistributionError("wheel members are duplicate or not sorted")
        if set(names) != expected_files:
            raise DistributionError(
                f"wheel inventory {sorted(names)} != {sorted(expected_files)}"
            )
        for item in items:
            safe_parts(item.filename)
            if item.is_dir():
                raise DistributionError(f"wheel has a directory entry: {item.filename}")
            mode = (item.external_attr >> 16) & 0o777
            if item.create_system != 3 or mode != 0o644:
                raise DistributionError(f"wheel mode is not canonical: {item.filename}")
            if item.date_time != expected_timestamp:
                raise DistributionError(f"wheel timestamp differs: {item.filename}")
            _forbidden(archive.read(item), root=root, source=item.filename)

        project_document = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8")
        )
        project = project_document.get("project")
        if not isinstance(project, dict):
            raise DistributionError("source project metadata is missing")
        readme = (root / "README.md").read_text(encoding="utf-8")
        _metadata(
            archive.read(f"{dist_info}/METADATA"),
            version=version,
            readme=readme,
            project=project,
        )
        if (
            archive.read(f"{dist_info}/licenses/LICENSE")
            != (root / "LICENSE").read_bytes()
        ):
            raise DistributionError("wheel license differs from LICENSE")
        if archive.read("ssh_wrapper/py.typed") not in {b"", b"\n"}:
            raise DistributionError("py.typed must remain an empty marker")
        if archive.read(f"{dist_info}/top_level.txt") != b"ssh_wrapper\n":
            raise DistributionError("wheel top_level.txt differs")
        setuptools = read_input(root / "requirements-package.in").get("setuptools")
        expected_wheel_metadata = (
            "Wheel-Version: 1.0\n"
            f"Generator: setuptools ({setuptools})\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n\n"
        )
        if (
            setuptools is None
            or archive.read(f"{dist_info}/WHEEL").decode("utf-8")
            != expected_wheel_metadata
        ):
            raise DistributionError("wheel metadata or pure py3-none-any tag differs")

        record_path = f"{dist_info}/RECORD"
        rows = list(csv.reader(io.StringIO(archive.read(record_path).decode("utf-8"))))
        if (
            len(rows) != len(expected_files)
            or {row[0] for row in rows} != expected_files
        ):
            raise DistributionError("wheel RECORD inventory differs")
        for name, digest, size in rows:
            if name == record_path:
                if digest or size:
                    raise DistributionError("wheel RECORD self-entry must be unhashed")
                continue
            data = archive.read(name)
            encoded = (
                base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                .rstrip(b"=")
                .decode()
            )
            if digest != f"sha256={encoded}" or size != str(len(data)):
                raise DistributionError(f"wheel RECORD mismatch for {name}")


def verify_sdist(path: Path, *, root: Path, version: str, epoch: int) -> None:
    """Verify the normalized source archive and its exact file inventory."""
    archive_root = f"ssh_wrapper-{version}"
    package_files = {f"ssh_wrapper/{name}" for name in MODULES}
    egg_info_files = {
        "ssh_wrapper.egg-info/PKG-INFO",
        "ssh_wrapper.egg-info/SOURCES.txt",
        "ssh_wrapper.egg-info/dependency_links.txt",
        "ssh_wrapper.egg-info/top_level.txt",
    }
    expected_files = {
        ".version",
        "CHANGELOG.md",
        "LICENSE",
        "MANIFEST.in",
        "PKG-INFO",
        "README.md",
        "pyproject.toml",
        "setup.cfg",
        *package_files,
        *egg_info_files,
    }
    raw = path.read_bytes()
    if (
        len(raw) < 10
        or raw[:2] != b"\x1f\x8b"
        or struct.unpack("<I", raw[4:8])[0] != epoch
    ):
        raise DistributionError("sdist gzip header timestamp differs")
    if raw[3] & 0x08:
        raise DistributionError("sdist gzip header embeds a filename")

    with tarfile.open(path, mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)) or names != sorted(names):
            raise DistributionError("sdist members are duplicate or not sorted")
        files: dict[str, bytes] = {}
        directories: set[str] = set()
        for member in members:
            parts = safe_parts(member.name)
            if parts[0] != archive_root:
                raise DistributionError(
                    f"sdist member has the wrong root: {member.name}"
                )
            if member.issym() or member.islnk() or member.isdev():
                raise DistributionError(
                    f"sdist contains a special member: {member.name}"
                )
            if member.uid != 0 or member.gid != 0 or member.uname or member.gname:
                raise DistributionError(f"sdist ownership differs: {member.name}")
            if member.mtime != epoch or any(
                key in member.pax_headers for key in ("atime", "ctime", "mtime")
            ):
                raise DistributionError(f"sdist timestamp differs: {member.name}")
            relative = "/".join(parts[1:])
            if member.isdir():
                if member.mode != 0o755:
                    raise DistributionError(
                        f"sdist directory mode differs: {member.name}"
                    )
                directories.add(relative)
            elif member.isfile():
                if member.mode != 0o644:
                    raise DistributionError(f"sdist file mode differs: {member.name}")
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise DistributionError(f"cannot read sdist member: {member.name}")
                files[relative] = extracted.read()
            else:
                raise DistributionError(f"sdist member type differs: {member.name}")
        if set(files) != expected_files:
            raise DistributionError(
                f"sdist inventory {sorted(files)} != {sorted(expected_files)}"
            )
        if directories != {"", "ssh_wrapper", "ssh_wrapper.egg-info"}:
            raise DistributionError(
                f"sdist directory inventory differs: {sorted(directories)}"
            )

        for relative, data in files.items():
            _forbidden(data, root=root, source=relative)
        for name in (
            ".version",
            "CHANGELOG.md",
            "LICENSE",
            "MANIFEST.in",
            "README.md",
            "pyproject.toml",
        ):
            if files[name] != (root / name).read_bytes():
                raise DistributionError(f"sdist {name} differs from source")
        for name in MODULES:
            if (
                files[f"ssh_wrapper/{name}"]
                != (root / "ssh_wrapper" / name).read_bytes()
            ):
                raise DistributionError(f"sdist package file differs: {name}")
        if files["PKG-INFO"] != files["ssh_wrapper.egg-info/PKG-INFO"]:
            raise DistributionError("sdist PKG-INFO copies differ")
        if files["ssh_wrapper.egg-info/dependency_links.txt"] != b"\n":
            raise DistributionError("sdist dependency_links.txt differs")
        if files["ssh_wrapper.egg-info/top_level.txt"] != b"ssh_wrapper\n":
            raise DistributionError("sdist top_level.txt differs")
        if files["setup.cfg"] != b"[egg_info]\ntag_build = \ntag_date = 0\n\n":
            raise DistributionError("sdist setup.cfg differs")
        expected_sources = expected_files - {"PKG-INFO", "setup.cfg"}
        actual_sources = (
            files["ssh_wrapper.egg-info/SOURCES.txt"].decode("utf-8").splitlines()
        )
        if (
            len(actual_sources) != len(set(actual_sources))
            or set(actual_sources) != expected_sources
        ):
            raise DistributionError("sdist SOURCES.txt inventory differs")

        project_document = tomllib.loads(files["pyproject.toml"].decode("utf-8"))
        project = project_document.get("project")
        if not isinstance(project, dict):
            raise DistributionError("sdist project metadata is missing")
        readme = (root / "README.md").read_text(encoding="utf-8")
        _metadata(files["PKG-INFO"], version=version, readme=readme, project=project)


def verify(directory: Path, *, root: Path, epoch: int) -> tuple[Path, Path]:
    """Verify the exact wheel/sdist pair and optional checksum inventory."""
    version = (root / ".version").read_text(encoding="utf-8").strip()
    wheel = directory / f"ssh_wrapper-{version}-py3-none-any.whl"
    sdist = directory / f"ssh_wrapper-{version}.tar.gz"
    actual = {path.name for path in directory.iterdir() if path.is_file()}
    expected = {wheel.name, sdist.name}
    if actual not in (expected, expected | {"SHA256SUMS.txt"}):
        raise DistributionError(
            f"local distribution inventory differs: {sorted(actual)}"
        )
    if (directory / "SHA256SUMS.txt").is_file():
        verify_checksums(directory, version=version)
    for path in (wheel, sdist):
        if not path.is_file() or path.stat().st_size <= 0:
            raise DistributionError(f"distribution is missing or empty: {path.name}")
        if path.stat().st_mode & 0o777 != 0o644:
            raise DistributionError(f"distribution mode differs: {path.name}")
    verify_wheel(wheel, root=root, version=version, epoch=epoch)
    verify_sdist(sdist, root=root, version=version, epoch=epoch)
    return wheel, sdist


def main() -> int:
    """Verify one distribution directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--epoch", type=int, required=True)
    arguments = parser.parse_args()
    try:
        wheel, sdist = verify(
            arguments.directory.resolve(),
            root=arguments.root.resolve(),
            epoch=arguments.epoch,
        )
    except (
        OSError,
        tarfile.TarError,
        zipfile.BadZipFile,
        PolicyError,
        DistributionError,
    ) as error:
        print(f"distribution error: {error}", file=sys.stderr)
        return 1
    print(f"Verified {wheel.name} and {sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
