"""Punto de entrada de la API (§4.2, §17).

FastAPI + Pydantic, API REST versionada, errores normalizados, OpenAPI.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings, validate_startup
from app.core.errors import AppError, app_error_handler, error_response, unhandled_error_handler
from app.core.logging import configure_logging, get_logger
from app.core.observability import RequestContextMiddleware
from app.db.session import initialize_database
from app.db.transaction import TransactionMiddleware
from app.services.job_runner import reset_job_runner
from app.services.usage_service import organization_health


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    logger = get_logger("app.startup")
    for warning in validate_startup(get_settings()):
        log = logger.error if warning.startswith("CRÍTICO") else logger.warning
        log("config_check %s", warning)
    initialize_database()
    yield
    reset_job_runner()


async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        AppError(
            "Datos de entrada inválidos.",
            code="validation_error",
            status_code=422,
            details={"errors": exc.errors()},
        )
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.product_name,
        version="0.1.0-mvp",
        description="Plataforma SaaS de análisis y evolución de software. MVP: flujo estático de código fuente.",
        lifespan=lifespan,
    )
    app.add_middleware(TransactionMiddleware)
    app.add_middleware(
        RequestContextMiddleware,
        api_limit=settings.rate_limit_api_per_minute,
        auth_limit=settings.rate_limit_auth_per_minute,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)  # type: ignore[arg-type]
    app.include_router(api_router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "product": settings.product_short_name}

    @app.get("/health/ready", tags=["meta"])
    def readiness() -> JSONResponse:
        checks = organization_health()
        ready = checks.get("database") == "ok"
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"status": "ready" if ready else "not_ready", "checks": checks},
        )

    @app.get("/", include_in_schema=False, tags=["meta"])
    def root() -> HTMLResponse:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="utf-8">
            <title>SIREP API</title>
            <style>
                body {font-family:system-ui,sans-serif;background:#f8f9fa;color:#212529;
                      display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
                .card {background:#fff;padding:2rem 3rem;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,.1);
                       text-align:center;max-width:500px;}
                h1 {margin:0 0 .5rem;font-size:2rem;}
                p {margin:.5rem 0;}
                a {color:#0d6efd;text-decoration:none;}
                a:hover {text-decoration:underline;}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🚀 SIREP API</h1>
                <p>La API está corriendo correctamente.</p>
                <p><a href="/docs">📖 Documentación Swagger (OpenAPI)</a></p>
                <p><a href="/health">❤️ Health check</a></p>
                <p><a href="/health/ready">🔎 Readiness</a></p>
            </div>
        </body>
        </html>
        """)

    return app


app = create_app()
