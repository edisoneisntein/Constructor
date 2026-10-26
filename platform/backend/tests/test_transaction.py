"""Borde transaccional: una escritura 2xx debe ser visible al recibir la respuesta (§4.4).

Regresión: con el teardown de dependencias ``yield`` el ``commit`` ocurría después
de enviar la respuesta, provocando 401 intermitentes al reutilizar la sesión.
"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from tests.conftest import register


def test_session_visible_immediately_after_register(client: TestClient, tmp_path):
    session = register(client, "tx@example.com", "TX Org")

    db_path = tmp_path / "db.sqlite3"
    connection = sqlite3.connect(db_path)
    try:
        total = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        user = session["user"]["id"]
        for_user = connection.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user,)
        ).fetchone()[0]
    finally:
        connection.close()

    assert total >= 1
    assert for_user == 1


def test_authenticated_request_succeeds_immediately_after_register(client: TestClient):
    session = register(client, "tx2@example.com", "TX2 Org")
    headers = {"Authorization": f"Bearer {session['token']}"}
    for _ in range(5):
        response = client.get("/api/v1/projects", headers=headers)
        assert response.status_code == 200, response.text
