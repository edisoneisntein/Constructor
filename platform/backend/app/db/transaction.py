"""Borde transaccional por petición (§4.4).

Las dependencias con ``yield`` se limpian *después* de enviar la respuesta, por lo
que un ``commit`` en su teardown puede ejecutarse cuando el cliente ya recibió el
2xx y lanzó la siguiente petición (carrera: la escritura aún no es visible). Este
middleware confirma la conexión de la petición **antes** de devolver la respuesta,
garantizando que una escritura sea visible cuando el cliente recibe el éxito.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TransactionMiddleware(BaseHTTPMiddleware):
    """Confirma la conexión de la petición antes de enviar la respuesta."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        connection = getattr(request.state, "db_conn", None)
        if connection is not None and response.status_code < 400:
            connection.commit()
        return response
