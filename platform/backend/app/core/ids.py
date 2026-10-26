"""Identificadores y reloj únicos, con formato estable y trazable."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def new_id(prefix: str) -> str:
    """Genera un identificador ordenable por tiempo con prefijo semántico.

    Ejemplo: ``prj_1a2b3c4d5e6f``.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    random_part = "".join(secrets.choice(_ALPHABET) for _ in range(10))
    return f"{prefix}_{stamp}{random_part}"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_after(seconds: int) -> str:
    from datetime import timedelta

    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def is_expired(expires_at: str) -> bool:
    try:
        deadline = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline < datetime.now(timezone.utc)
