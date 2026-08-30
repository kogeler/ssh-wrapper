# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""MkDocs hooks for stable repository evidence links and root site files."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

REPOSITORY_BLOB = "https://github.com/kogeler/ssh-wrapper/blob/main"
_LINK_PATTERN = re.compile(r"\]\((?P<target>(?:\.\./)+[^)#]+)(?P<fragment>#[^)]*)?\)")


def on_page_markdown(
    markdown: str, *, page: Any, config: Any, **_kwargs: object
) -> str:
    """Rewrite links leaving docs_dir to stable repository blob links."""

    source_dir = Path(page.file.abs_src_path).parent
    docs_dir = Path(config["docs_dir"]).resolve()
    repository = docs_dir.parent

    def replace(match: re.Match[str]) -> str:
        target = match.group("target")
        resolved = (source_dir / target).resolve()
        try:
            resolved.relative_to(docs_dir)
        except ValueError:
            try:
                repository_path = resolved.relative_to(repository).as_posix()
            except ValueError:
                return match.group(0)
            fragment = match.group("fragment") or ""
            return f"]({REPOSITORY_BLOB}/{repository_path}{fragment})"
        return match.group(0)

    return _LINK_PATTERN.sub(replace, markdown)


def on_post_build(*, config: Any, **_kwargs: object) -> None:
    """Publish non-page inputs at the GitHub Pages project-site root."""

    docs_dir = Path(config["docs_dir"])
    site_dir = Path(config["site_dir"])
    for name in ("llms.txt", "robots.txt"):
        shutil.copyfile(docs_dir / "site" / name, site_dir / name)

