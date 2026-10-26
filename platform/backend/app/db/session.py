"""Singleton de base de datos e inicialización de esquema."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.ids import utcnow_iso
from app.db.database import Database

_db: Database | None = None


def get_database() -> Database:
    global _db
    if _db is None:
        settings = get_settings()
        _db = Database(settings.database_url or settings.database_path)
    return _db


def reset_database() -> None:
    """Uso exclusivo en pruebas."""
    global _db
    _db = None


def initialize_database() -> Database:
    database = get_database()
    database.initialize(utcnow_iso())
    return database
