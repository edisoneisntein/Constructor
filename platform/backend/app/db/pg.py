"""Adaptador de conexión PostgreSQL (§4.4).

Objetivo: ejecutar las **mismas** consultas parametrizadas escritas para SQLite
sobre PostgreSQL sin tocar la lógica de negocio. El adaptador:

- Traduce los marcadores posicionales ``?`` a ``%s`` y los nombrados ``:name`` a
  ``%(name)s`` (según el tipo de parámetros).
- Traduce ``INSERT OR IGNORE INTO`` a ``INSERT ... ON CONFLICT DO NOTHING``.
- Devuelve filas tipo diccionario (``row["col"]``), homogéneas con ``sqlite3.Row``.

No interpreta la semántica de las consultas: solo sustituye marcadores. Los
marcadores nunca aparecen dentro de literales en este proyecto.
"""

from __future__ import annotations

import re

_NAMED_PARAM = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")


def translate_query(sql: str, *, named: bool) -> str:
    """Traduce una consulta de estilo SQLite a PostgreSQL."""
    translated = sql
    if "INSERT OR IGNORE INTO" in translated:
        translated = translated.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        if "ON CONFLICT" not in translated:
            translated = translated.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    if named:
        translated = _NAMED_PARAM.sub(r"%(\1)s", translated)
    else:
        translated = translated.replace("?", "%s")
    return translated


class PostgresConnection:
    """Envoltura fina sobre ``psycopg.Connection`` con traducción de consultas."""

    def __init__(self, connection) -> None:  # noqa: ANN001 - psycopg.Connection
        self._connection = connection

    def execute(self, sql: str, params=None):  # noqa: ANN001
        named = isinstance(params, dict)
        statement = translate_query(sql, named=named)
        if params is None:
            return self._connection.execute(statement)
        return self._connection.execute(statement, params)

    def executemany(self, sql: str, seq_of_params):  # noqa: ANN001
        params = list(seq_of_params)
        named = bool(params) and isinstance(params[0], dict)
        cursor = self._connection.cursor()
        cursor.executemany(translate_query(sql, named=named), params)
        return cursor

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> PostgresConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._connection.commit()
        else:
            self._connection.rollback()
