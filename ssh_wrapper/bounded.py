# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Small bounded byte containers for local process supervisors."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TAIL_BYTES = 16 * 1024


@dataclass(slots=True)
class BoundedTail:
    """Keep only the final bounded bytes from a continuously drained stream."""

    limit: int = DEFAULT_TAIL_BYTES
    data: bytes = b""

    def append(self, chunk: bytes) -> None:
        """Append bytes while retaining only the configured tail."""
        self.data = (self.data + chunk)[-self.limit :]

    def clear(self) -> None:
        """Discard all retained diagnostics."""
        self.data = b""

    def text(self) -> str:
        """Decode the diagnostic tail without failing on binary output."""
        return self.data.decode("utf-8", errors="replace")
