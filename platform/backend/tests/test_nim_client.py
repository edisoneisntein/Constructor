"""Integración con NVIDIA NIM (§12/§13): único proveedor de IA de la plataforma."""

from __future__ import annotations

import json
import os

import httpx
import pytest

from app.core.config import get_settings
from app.engines.migration.nim_client import NimClient, NimError
from app.services.migration_service import build_nim_client, verify_nim_connection

MODELS = {
    "data": [
        {"id": "nvidia/nemotron-3-super-120b-a12b"},
        {"id": "nvidia/nemotron-3-embed-1b"},
    ]
}


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json=MODELS)
    if request.url.path.endswith("/chat/completions"):
        return httpx.Response(
            200,
            json={
                "model": "nvidia/nemotron-3-super-120b-a12b",
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
                "usage": {"total_tokens": 7},
            },
        )
    return httpx.Response(404, json={"error": {"message": "not found"}})


def _transport() -> httpx.MockTransport:
    return httpx.MockTransport(_handler)


def test_list_models_and_chat_with_fake_transport():
    client = NimClient(base_url="https://nim.test/v1", api_key="secret", transport=_transport())
    assert client.configured is True
    assert client.list_models() == [
        "nvidia/nemotron-3-embed-1b",
        "nvidia/nemotron-3-super-120b-a12b",
    ]
    result = client.chat([{"role": "user", "content": "hi"}], model="nvidia/nemotron-3-super-120b-a12b")
    assert result.content == "OK"
    assert result.usage["total_tokens"] == 7


def test_client_reports_http_errors():
    def error_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "unauthorized"}})

    client = NimClient(
        base_url="https://nim.test/v1", api_key="bad", transport=httpx.MockTransport(error_handler)
    )
    with pytest.raises(NimError) as excinfo:
        client.list_models()
    assert excinfo.value.status_code == 401


def test_verify_reports_missing_key():
    settings = get_settings().model_copy(update={"nim_api_key": None})
    report = verify_nim_connection(settings, transport=_transport())
    assert report["configured"] is False
    assert report["error"] == "missing_api_key"


def test_verify_reports_models_and_completion():
    settings = get_settings().model_copy(
        update={"nim_api_key": "secret", "nim_model": "nvidia/nemotron-3-super-120b-a12b"}
    )
    report = verify_nim_connection(settings, transport=_transport())
    assert report["configured"] and report["reachable"] and report["model_available"]
    assert report["completion_ok"] is True
    assert report["models_count"] == 2


def test_verify_marks_unavailable_model():
    settings = get_settings().model_copy(
        update={"nim_api_key": "secret", "nim_model": "acme/does-not-exist"}
    )
    report = verify_nim_connection(settings, transport=_transport())
    assert report["reachable"] is True
    assert report["model_available"] is False
    assert report["completion_ok"] is False


def test_build_nim_client_uses_settings():
    settings = get_settings().model_copy(
        update={"nim_api_key": "secret", "nim_base_url": "https://integro.test/v1"}
    )
    client = build_nim_client(settings, transport=_transport())
    assert client.base_url == "https://integro.test/v1"
    assert client.api_key == "secret"


@pytest.mark.skipif(
    os.environ.get("SIREP_NIM_LIVE_TEST") != "1",
    reason="Prueba en vivo: requiere SIREP_NIM_LIVE_TEST=1 y SIREP_NIM_API_KEY.",
)
def test_live_nim_verification():
    report = verify_nim_connection(get_settings())
    assert report["configured"] is True, report
    assert report["reachable"] is True, report
    assert report["model_available"] is True, json.dumps(report, indent=2)
    assert report["completion_ok"] is True, json.dumps(report, indent=2)
