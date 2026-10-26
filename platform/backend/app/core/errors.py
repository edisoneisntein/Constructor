"""Errores normalizados (§17: errores normalizados; §23: estados explícitos).

Toda respuesta de error de la API sigue el contrato:

    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Error de aplicación con código estable y estado HTTP."""

    code = "internal_error"
    status_code = 500
    message = "Error interno."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details or {}
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class ValidationAppError(AppError):
    code = "validation_error"
    status_code = 422
    message = "Datos de entrada inválidos."


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404
    message = "Recurso no encontrado."


class UnauthorizedError(AppError):
    code = "unauthorized"
    status_code = 401
    message = "Autenticación requerida."


class ForbiddenError(AppError):
    code = "forbidden"
    status_code = 403
    message = "Permiso denegado."


class ConflictError(AppError):
    code = "conflict"
    status_code = 409
    message = "Conflicto con el estado actual."


class PayloadTooLargeError(AppError):
    code = "payload_too_large"
    status_code = 413
    message = "El contenido supera el límite permitido."


class UnsafeArchiveError(AppError):
    code = "unsafe_archive"
    status_code = 400
    message = "El archivo contiene entradas no seguras."


class QuotaExceededError(AppError):
    code = "quota_exceeded"
    status_code = 403
    message = "Se superó la cuota de la organización."


class RateLimitedError(AppError):
    code = "rate_limited"
    status_code = 429
    message = "Demasiadas solicitudes; intente más tarde."


class CapabilityUnavailableError(AppError):
    code = "capability_unavailable"
    status_code = 503
    message = "La capacidad solicitada no está disponible en este entorno."


def error_response(error: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message, "details": error.details}},
    )


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc)


async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # No se filtran detalles internos al cliente (§3.3).
    return error_response(AppError("Error interno no controlado."))
