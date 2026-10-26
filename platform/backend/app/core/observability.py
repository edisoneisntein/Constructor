"""Observabilidad y límites por petición (§14, §19.6, §21 Fase 11).

Middleware que asigna un identificador de correlación (``X-Request-ID``), mide la
duración, registra de forma estructurada y aplica límites de tasa multiusuario.

§14: la identidad usada para el límite de tasa **nunca** se toma de una
cabecera controlada por el cliente. Antes se usaba ``X-Organization-Id``, lo que
permitía evadir el límite rotando arbitrariamente ese valor. Ahora la
identidad se deriva de:

* la dirección IP de origen (``request.client.host``), y
* el hash del token de sesión, cuando la petición va autenticada.

Ambas son intrínsecamente estables y no controlables por el cliente: no se
pueden inventar cubos nuevos sin presentar credenciales válidas.

La cabecera ``X-Organization-Id`` sigue existiendo, pero **solo** para resolver
la organización activa, y siempre tras validar la pertenencia del usuario
(``api/deps.py``). No participa en la identidad del limitador.

Limitación honesta: los límites de tasa son en proceso (una instancia); ver
``core/rate_limit.py``.
"""

from __future__ import annotations

import hashlib
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import RateLimitedError, error_response
from app.core.logging import get_logger
from app.core.rate_limit import check_rate_limit

_logger = get_logger("http")

_SKIP_RATE_LIMIT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")


def _client_identity(request: Request) -> str:
    """Identidad de origen estable, no controlable por el cliente."""
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _session_identity(request: Request) -> str | None:
    """Identidad de sesión (hash del token) si la petición va autenticada.

    Se usa el hash, nunca el token en claro, para no filtrar credenciales en
    las claves del limitador.
    """
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    digest = hashlib.sha256(token.strip().encode("utf-8")).hexdigest()
    return digest[:32]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Correlación, medición y límites de tasa por petición."""

    def __init__(self, app, *, api_limit: int, auth_limit: int, window_seconds: int = 60) -> None:
        super().__init__(app)
        self.api_limit = api_limit
        self.auth_limit = auth_limit
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        path = request.url.path

        if not any(path.startswith(prefix) for prefix in _SKIP_RATE_LIMIT_PREFIXES):
            bucket = "auth" if path.startswith("/api/v1/auth") else "api"
            limit = self.auth_limit if bucket == "auth" else self.api_limit
            identities = [f"{bucket}:ip:{_client_identity(request)}"]
            session = _session_identity(request)
            if session is not None:
                identities.append(f"{bucket}:session:{session}")
            for identity in identities:
                result = check_rate_limit(
                    identity, limit=limit, window_seconds=self.window_seconds
                )
                if not result.allowed:
                    response = error_response(
                        RateLimitedError(
                            details={
                                "bucket": bucket,
                                "retry_after_seconds": result.retry_after_seconds,
                            }
                        )
                    )
                    response.headers["Retry-After"] = str(result.retry_after_seconds)
                    response.headers["X-Request-ID"] = request_id
                    return response

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        _logger.info(
            "request method=%s path=%s status=%s duration_ms=%s request_id=%s",
            request.method,
            path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response
