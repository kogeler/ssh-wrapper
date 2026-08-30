# Copyright (c) 2026 kogeler
# SPDX-License-Identifier: MIT

"""Stable failures returned by SSH wrapper operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SSHError(Exception):
    """An expected failure with a stable machine-readable identifier."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def to_dict(self) -> dict[str, Any]:
        """Return the existing structured error representation."""
        result: dict[str, Any] = {"error": self.code, "message": self.message}
        if self.details:
            result["details"] = self.details
        return result
