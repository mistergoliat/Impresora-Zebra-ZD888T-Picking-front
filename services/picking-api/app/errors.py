"""Utilities for consistent API error responses."""

from __future__ import annotations

from fastapi import HTTPException


def api_error(status_code: int, code: str, detail: str, *, headers: dict[str, str] | None = None) -> HTTPException:
    """Create an :class:`HTTPException` with a normalized payload."""

    payload = {"code": code, "detail": detail}
    return HTTPException(status_code=status_code, detail=payload, headers=headers)
