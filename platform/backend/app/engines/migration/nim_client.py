"""Cliente mínimo de NVIDIA NIM (API compatible con OpenAI) (§12/§13).

Proveedor único de IA de la plataforma: **NVIDIA NIM**. No se integra Gemini.
El endpoint es configurable (§12.3 del PDF) y las credenciales siempre provienen
del entorno (``SIREP_NIM_API_KEY``); nunca se hardcodean ni se registran.

Operaciones cubiertas por NIM (OpenAI-compatible):
  * ``GET  {base}/models``             → modelos servidos.
  * ``POST {base}/chat/completions``   → inferencia de chat.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

DEFAULT_TIMEOUT_SECONDS = 30.0


class NimError(RuntimeError):
    """Error de comunicación o de autenticación con NIM."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class NimChatResult:
    content: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    reasoning: str | None = None
    latency_ms: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


class NimClient:
    """Cliente HTTP para NVIDIA NIM. Inyecta ``transport`` para pruebas."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _client(self) -> httpx.Client:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout_seconds,
            transport=self._transport,
        )

    def list_models(self) -> list[str]:
        with self._client() as client:
            response = client.get("/models")
            self._raise_for_status(response)
            payload = response.json()
        return sorted(item.get("id", "") for item in payload.get("data", []) if item.get("id"))

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.2,
        top_p: float = 1.0,
        extra: dict[str, Any] | None = None,
    ) -> NimChatResult:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
            # Los modelos Nemotron de NIM son de razonamiento: sin desactivarlo agotan
            # los tokens en `reasoning_content` y `content` vuelve vacío
            # ("El modelo devolvió una respuesta vacía"). Los modelos que no
            # entienden esta clave la ignoran.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if extra:
            body.update(extra)
        started = time.monotonic()
        with self._client() as client:
            response = client.post("/chat/completions", json=body)
            self._raise_for_status(response)
            payload = response.json()
        latency_ms = round((time.monotonic() - started) * 1000, 2)
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return NimChatResult(
            content=message.get("content") or "",
            reasoning=message.get("reasoning_content"),
            model=payload.get("model", model),
            usage=payload.get("usage") or {},
            latency_ms=latency_ms,
            raw=payload,
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code >= 400:
            detail = ""
            try:
                detail = response.json().get("error", {}).get("message") or response.text
            except Exception:  # noqa: BLE001
                detail = response.text
            raise NimError(
                f"NIM respondió {response.status_code}: {detail[:300]}",
                status_code=response.status_code,
            )
