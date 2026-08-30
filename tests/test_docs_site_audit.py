# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Tests for the generated project-site documentation audit."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from tools.audit_docs_site import AuditError, audit_site

SITE_URL = "https://kogeler.github.io/ssh-wrapper/"


def _write_site(root: Path, *, body: str = '<a href="#start">Start</a>') -> None:
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <title>Documentation</title>
    <link rel="canonical" href="{SITE_URL}">
    <link rel="stylesheet" href="assets/site.css">
  </head>
  <body><h1 id="start">Documentation</h1>{body}</body>
</html>
"""
    (root / "assets").mkdir(parents=True, exist_ok=True)
    (root / "assets/site.css").write_text("body { color: black; }\n", encoding="utf-8")
    (root / "index.html").write_text(html, encoding="utf-8")
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{SITE_URL}</loc></url>
</urlset>
""".encode()
    (root / "sitemap.xml").write_bytes(sitemap)
    (root / "sitemap.xml.gz").write_bytes(gzip.compress(sitemap, mtime=0))
    (root / "llms.txt").write_text(
        f"# ssh-wrapper\n\nCanonical documentation: {SITE_URL}\n\n"
        "Start with:\n- /ssh-wrapper/\n",
        encoding="utf-8",
    )
    (root / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n",
        encoding="utf-8",
    )


def test_generated_site_audit_accepts_complete_project_site(tmp_path: Path) -> None:
    _write_site(tmp_path)

    assert audit_site(tmp_path, SITE_URL) == (1, 3)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('<a href="missing/">Missing</a>', "target does not exist"),
        ('<a href="#missing">Missing</a>', "missing anchor"),
        ('<img src="assets/missing.png">', "missing an alt attribute"),
        (
            '<a href="https://kogeler.github.io/other/">Outside</a>',
            "leaves project site",
        ),
        (
            '<a href="http://kogeler.github.io/ssh-wrapper/">HTTP</a>',
            "insecure HTTP reference",
        ),
    ],
)
def test_generated_site_audit_rejects_invalid_output(
    tmp_path: Path, body: str, message: str
) -> None:
    _write_site(tmp_path, body=body)

    with pytest.raises(AuditError, match=message):
        audit_site(tmp_path, SITE_URL)


def test_generated_site_audit_rejects_incorrect_gzip_or_robots(
    tmp_path: Path,
) -> None:
    _write_site(tmp_path)
    (tmp_path / "sitemap.xml.gz").write_bytes(b"not gzip")
    with pytest.raises(AuditError, match="invalid compressed sitemap"):
        audit_site(tmp_path, SITE_URL)

    _write_site(tmp_path)
    (tmp_path / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://example.invalid/sitemap.xml\n",
        encoding="utf-8",
    )
    with pytest.raises(AuditError, match="does not advertise"):
        audit_site(tmp_path, SITE_URL)


def test_generated_site_audit_rejects_stale_llms_route(tmp_path: Path) -> None:
    _write_site(tmp_path)
    (tmp_path / "llms.txt").write_text(
        f"# ssh-wrapper\n\nCanonical documentation: {SITE_URL}\n\n"
        "Start with:\n- /ssh-wrapper/missing/\n",
        encoding="utf-8",
    )

    with pytest.raises(AuditError, match="llms.txt route does not exist"):
        audit_site(tmp_path, SITE_URL)
