"""Configuración central del producto.

Corresponde a §0 (nombre parametrizable) y §4 (stack/entorno) del PDF SAAS REA.
Todos los límites son configurables por variables de entorno con prefijo SIREP_.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

try:  # Carga local de credenciales desde .env (nunca versionado).
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
except Exception:  # noqa: BLE001 - dotenv es opcional
    pass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return float(raw)


class Settings(BaseModel):
    """Configuración inmutable cargada desde el entorno."""

    # §0: el nombre del producto debe poder cambiarse sin tocar el núcleo.
    product_name: str = Field(
        default="Software Intelligence, Reconstruction & Evolution Platform"
    )
    product_short_name: str = Field(default="SIREP")
    product_slug: str = Field(default="sirep")
    environment: str = Field(default="development")

    # Persistencia (§4.4): ruta del archivo SQLite para el MVP.
    database_path: Path = Field(default=Path("var/sirep.sqlite3"))
    # URL de PostgreSQL; si se define, prevalece sobre ``database_path`` (§4.4).
    database_url: str | None = Field(default=None)

    # Almacenamiento de artefactos y workspaces (§4.5 / §14).
    storage_root: Path = Field(default=Path("var/storage"))

    # Autenticación (§16 User / OrganizationMembership).
    session_ttl_seconds: int = Field(default=60 * 60 * 24 * 7)
    password_min_length: int = Field(default=10)
    # Bypass de autenticación SOLO para desarrollo local. Nunca se activa por
    # defecto y está prohibido en entornos de producción (ver ``validate_startup``).
    dev_auth_bypass: bool = Field(default=False)

    # Límites de ingesta segura (§14.3 / §4.5).
    max_upload_bytes: int = Field(default=100 * 1024 * 1024)  # 100 MiB
    max_extracted_bytes: int = Field(default=500 * 1024 * 1024)  # 500 MiB
    max_archive_entries: int = Field(default=20_000)
    max_compression_ratio: float = Field(default=100.0)
    max_path_depth: int = Field(default=64)
    max_single_file_bytes: int = Field(default=20 * 1024 * 1024)  # 20 MiB
    # Ingesta de carpetas (§14.3 / §4.5): árbol de archivos con rutas relativas.
    max_ingest_files: int = Field(default=5_000)
    max_ingest_total_bytes: int = Field(default=500 * 1024 * 1024)  # 500 MiB
    max_ingest_file_bytes: int = Field(default=20 * 1024 * 1024)  # 20 MiB
    max_ingest_path_depth: int = Field(default=64)
    max_ingest_path_length: int = Field(default=4096)

    # Análisis (§5): límites de recursos.
    analysis_max_file_bytes: int = Field(default=2 * 1024 * 1024)  # no analizar > 2 MiB
    analysis_timeout_seconds: int = Field(default=300)
    binary_analysis_max_bytes: int = Field(default=64 * 1024 * 1024)  # §6.2: tope de lectura del binario
    workspace_retention_seconds: int = Field(default=3600)  # limpieza de temporales

    # Adaptador REA (§3.3): ruta opcional al ejecutable rea.
    rea_binary: str | None = Field(default=None)
    rea_enabled: bool = Field(default=True)
    rea_timeout_seconds: int = Field(default=180)

    # Red / CORS.
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    # Seguridad y aislamiento (§14).
    # §14.1: perfil de ejecución activo. El perfil más permisivo NUNCA se activa solo.
    # El valor por defecto es el perfil más seguro (sin ejecución de código del
    # proyecto). Los perfiles que ejecutan código deben habilitarse de forma
    # explícita vía SIREP_EXECUTION_PROFILE (ver §14.1 y FASE 19).
    execution_profile: str = Field(default="STATIC_ANALYSIS")
    execution_allow_high_risk: bool = Field(default=False)
    # §14.2: límites de recursos para subprocesos de código no confiable.
    sandbox_cpu_seconds: int = Field(default=120)
    sandbox_max_memory_mb: int = Field(default=0)  # 0 = no aplicar RLIMIT_AS (evita romper Node/V8)
    sandbox_max_file_bytes: int = Field(default=64 * 1024 * 1024)
    # Límites aplicados al ejecutar las pruebas del proyecto (comprobación
    # "pytest" del Implementation Validator). 0 = sin límite explícito.
    validation_cpu_seconds: int = Field(default=120)
    validation_timeout_seconds: int = Field(default=180)
    # §14.4: hosts externos autorizados para conexiones salientes (vacío = ninguno).
    outbound_allowed_hosts: list[str] = Field(default_factory=list)

    # §14/§21: cuotas por organización y límites de tasa multiusuario.
    org_max_projects: int = Field(default=25)
    org_max_storage_bytes: int = Field(default=2 * 1024 * 1024 * 1024)  # 2 GiB
    org_max_concurrent_jobs: int = Field(default=4)
    rate_limit_api_per_minute: int = Field(default=600)
    rate_limit_auth_per_minute: int = Field(default=30)
    # §14/§21: backend de limitación de tasa ("memory" en proceso | "database" compartido | "redis" externo).
    rate_limit_backend: str = Field(default="memory")
    # Configuración opcional cuando el backend es "redis".
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)

    # §4.3/§21: ejecución de trabajos asíncronos. "inline" usa un pool de hilos
    # en el proceso de la API; "external" deja los trabajos en QUEUED para que
    # los consuma un proceso trabajador (`python -m app.worker`), permitiendo
    # escalar horizontalmente el número de workers.
    job_queue_backend: str = Field(default="inline")
    worker_id: str | None = Field(default=None)
    worker_poll_interval_seconds: float = Field(default=1.0)
    worker_claim_batch: int = Field(default=1)
    # Recuperación de trabajos huérfanos: un trabajo RUNNING sin latido durante
    # más de este tiempo se reencola (el worker pudo morir).
    job_stale_after_seconds: int = Field(default=600)
    job_max_attempts: int = Field(default=3)
    # §14.6: purga de retención programada dentro del worker (<=0 la desactiva).
    retention_purge_interval_seconds: float = Field(default=3600.0)

    # Transmisión externa de código a proveedores de IA (§13): consentimiento explícito.
    ai_transmission_consent_default: bool = Field(default=False)

    # Migración Gemini → NVIDIA NIM (§12.3): endpoint, modelo y credenciales
    # configurables. No se hardcodean secretos ni se asume una URL universal.
    nim_base_url: str = Field(default="https://integrate.api.nvidia.com/v1")
    nim_api_key: str | None = Field(default=None)
    nim_model: str = Field(default="nvidia/nemotron-3-super-120b-a12b")
    nim_timeout_seconds: float = Field(default=30.0)
    # Solo informativo: la plataforma NO integra Gemini (proveedor único = NIM).
    gemini_api_base_url: str = Field(default="https://generativelanguage.googleapis.com")

    # Cifrado simétrico de secretos en reposo (§14.6). En producción, clave desde
    # gestor de secretos. En desarrollo se deriva del entorno (nunca en el código).
    secret_key: str = Field(default="dev-insecure-change-me")


def _build_settings() -> Settings:
    root = Path(os.environ.get("SIREP_STORAGE_ROOT", "var/storage"))
    defaults = Settings()
    return Settings(
        product_name=os.environ.get("SIREP_PRODUCT_NAME", defaults.product_name),
        product_short_name=os.environ.get("SIREP_PRODUCT_SHORT_NAME", defaults.product_short_name),
        product_slug=os.environ.get("SIREP_PRODUCT_SLUG", defaults.product_slug),
        environment=os.environ.get("SIREP_ENV", defaults.environment),
        database_path=Path(os.environ.get("SIREP_DATABASE_PATH", str(defaults.database_path))),
        database_url=os.environ.get("SIREP_DATABASE_URL", defaults.database_url) or None,
        storage_root=root,
        session_ttl_seconds=_env_int("SIREP_SESSION_TTL_SECONDS", defaults.session_ttl_seconds),
        password_min_length=_env_int("SIREP_PASSWORD_MIN_LENGTH", defaults.password_min_length),
        dev_auth_bypass=_env_bool("SIREP_DEV_AUTH_BYPASS", defaults.dev_auth_bypass),
        max_upload_bytes=_env_int("SIREP_MAX_UPLOAD_BYTES", defaults.max_upload_bytes),
        max_extracted_bytes=_env_int("SIREP_MAX_EXTRACTED_BYTES", defaults.max_extracted_bytes),
        max_archive_entries=_env_int("SIREP_MAX_ARCHIVE_ENTRIES", defaults.max_archive_entries),
        max_compression_ratio=float(
            os.environ.get("SIREP_MAX_COMPRESSION_RATIO", str(defaults.max_compression_ratio))
        ),
        max_path_depth=_env_int("SIREP_MAX_PATH_DEPTH", defaults.max_path_depth),
        max_single_file_bytes=_env_int("SIREP_MAX_SINGLE_FILE_BYTES", defaults.max_single_file_bytes),
        max_ingest_files=_env_int("SIREP_MAX_INGEST_FILES", defaults.max_ingest_files),
        max_ingest_total_bytes=_env_int(
            "SIREP_MAX_INGEST_TOTAL_BYTES", defaults.max_ingest_total_bytes
        ),
        max_ingest_file_bytes=_env_int(
            "SIREP_MAX_INGEST_FILE_BYTES", defaults.max_ingest_file_bytes
        ),
        max_ingest_path_depth=_env_int(
            "SIREP_MAX_INGEST_PATH_DEPTH", defaults.max_ingest_path_depth
        ),
        max_ingest_path_length=_env_int(
            "SIREP_MAX_INGEST_PATH_LENGTH", defaults.max_ingest_path_length
        ),
        analysis_max_file_bytes=_env_int(
            "SIREP_ANALYSIS_MAX_FILE_BYTES", defaults.analysis_max_file_bytes
        ),
        binary_analysis_max_bytes=_env_int(
            "SIREP_BINARY_ANALYSIS_MAX_BYTES", defaults.binary_analysis_max_bytes
        ),
        analysis_timeout_seconds=_env_int(
            "SIREP_ANALYSIS_TIMEOUT_SECONDS", defaults.analysis_timeout_seconds
        ),
        workspace_retention_seconds=_env_int(
            "SIREP_WORKSPACE_RETENTION_SECONDS", defaults.workspace_retention_seconds
        ),
        rea_binary=os.environ.get("SIREP_REA_BINARY", defaults.rea_binary),
        rea_enabled=_env_bool("SIREP_REA_ENABLED", defaults.rea_enabled),
        rea_timeout_seconds=_env_int("SIREP_REA_TIMEOUT_SECONDS", defaults.rea_timeout_seconds),
        ai_transmission_consent_default=_env_bool(
            "SIREP_AI_TRANSMISSION_CONSENT", defaults.ai_transmission_consent_default
        ),
        nim_base_url=os.environ.get("SIREP_NIM_BASE_URL", defaults.nim_base_url),
        nim_api_key=os.environ.get("SIREP_NIM_API_KEY", defaults.nim_api_key),
        nim_model=os.environ.get("SIREP_NIM_MODEL", defaults.nim_model),
        nim_timeout_seconds=_env_float("SIREP_NIM_TIMEOUT_SECONDS", defaults.nim_timeout_seconds),
        gemini_api_base_url=os.environ.get(
            "SIREP_GEMINI_API_BASE_URL", defaults.gemini_api_base_url
        ),
        allowed_origins=_env_list("SIREP_ALLOWED_ORIGINS", defaults.allowed_origins),
        execution_profile=os.environ.get("SIREP_EXECUTION_PROFILE", defaults.execution_profile),
        execution_allow_high_risk=_env_bool(
            "SIREP_EXECUTION_ALLOW_HIGH_RISK", defaults.execution_allow_high_risk
        ),
        sandbox_cpu_seconds=_env_int("SIREP_SANDBOX_CPU_SECONDS", defaults.sandbox_cpu_seconds),
        sandbox_max_memory_mb=_env_int("SIREP_SANDBOX_MAX_MEMORY_MB", defaults.sandbox_max_memory_mb),
        sandbox_max_file_bytes=_env_int("SIREP_SANDBOX_MAX_FILE_BYTES", defaults.sandbox_max_file_bytes),
        validation_cpu_seconds=_env_int(
            "SIREP_VALIDATION_CPU_SECONDS", defaults.validation_cpu_seconds
        ),
        validation_timeout_seconds=_env_int(
            "SIREP_VALIDATION_TIMEOUT_SECONDS", defaults.validation_timeout_seconds
        ),
        outbound_allowed_hosts=_env_list("SIREP_OUTBOUND_ALLOWED_HOSTS", defaults.outbound_allowed_hosts),
        org_max_projects=_env_int("SIREP_ORG_MAX_PROJECTS", defaults.org_max_projects),
        org_max_storage_bytes=_env_int("SIREP_ORG_MAX_STORAGE_BYTES", defaults.org_max_storage_bytes),
        org_max_concurrent_jobs=_env_int("SIREP_ORG_MAX_CONCURRENT_JOBS", defaults.org_max_concurrent_jobs),
        rate_limit_api_per_minute=_env_int("SIREP_RATE_LIMIT_API_PER_MINUTE", defaults.rate_limit_api_per_minute),
        rate_limit_auth_per_minute=_env_int("SIREP_RATE_LIMIT_AUTH_PER_MINUTE", defaults.rate_limit_auth_per_minute),
        rate_limit_backend=os.environ.get("SIREP_RATE_LIMIT_BACKEND", defaults.rate_limit_backend),
        job_queue_backend=os.environ.get("SIREP_JOB_QUEUE", defaults.job_queue_backend),
        worker_id=os.environ.get("SIREP_WORKER_ID", defaults.worker_id),
        worker_poll_interval_seconds=_env_float(
            "SIREP_WORKER_POLL_SECONDS", defaults.worker_poll_interval_seconds
        ),
        worker_claim_batch=_env_int("SIREP_WORKER_CLAIM_BATCH", defaults.worker_claim_batch),
        job_stale_after_seconds=_env_int(
            "SIREP_JOB_STALE_AFTER_SECONDS", defaults.job_stale_after_seconds
        ),
        job_max_attempts=_env_int("SIREP_JOB_MAX_ATTEMPTS", defaults.job_max_attempts),
        retention_purge_interval_seconds=_env_float(
            "SIREP_RETENTION_PURGE_INTERVAL_SECONDS", defaults.retention_purge_interval_seconds
        ),
        secret_key=os.environ.get("SIREP_SECRET_KEY", defaults.secret_key),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = _build_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    (settings.storage_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (settings.storage_root / "workspaces").mkdir(parents=True, exist_ok=True)
    (settings.storage_root / "tmp").mkdir(parents=True, exist_ok=True)
    return settings


PRODUCTION_ENVIRONMENTS = frozenset({"production", "prod", "staging"})

# Máximo de partes de archivo que el parser multipart de Starlette acepta por
# defecto. La ingesta de carpetas parsea el formulario con límites explícitos,
# pero se avisa si la configuración los supera para no fallar en silencio.
STARLETTE_DEFAULT_MAX_FILES = 1000

# Secretos que nunca deben usarse fuera de desarrollo local.
_INSECURE_SECRET_KEYS = frozenset(
    {
        "dev-insecure-change-me",
        "change-me-in-production",
        "change-me",
        "secret",
    }
)


def validate_startup(settings: Settings) -> list[str]:
    """Valida la configuración al arrancar y devuelve los avisos detectados.

    No lanza excepciones: el llamador decide cómo reaccionar. Los modos de
    fallo se reportan en el log de arranque para que sean visibles.
    """
    warnings: list[str] = []
    environment = (settings.environment or "").strip().lower()

    if environment in PRODUCTION_ENVIRONMENTS:
        if settings.dev_auth_bypass:
            warnings.append(
                "CRÍTICO: SIREP_DEV_AUTH_BYPASS está activo en un entorno de "
                f"'{settings.environment}'. La autenticación está deshabilitada."
            )
        if settings.secret_key in _INSECURE_SECRET_KEYS or len(settings.secret_key) < 32:
            warnings.append(
                "CRÍTICO: SIREP_SECRET_KEY usa un valor por defecto o es demasiado "
                "corto (<32 caracteres) en un entorno de producción."
            )
        if settings.execution_allow_high_risk:
            warnings.append(
                "AVISO: SIREP_EXECUTION_ALLOW_HIGH_RISK está activo; el perfil de "
                "análisis dinámico de alto riesgo queda habilitado."
            )
        if settings.rate_limit_backend == "memory":
            warnings.append(
                "AVISO: el limitador de tasa 'memory' solo protege una instancia; "
                "usa 'database' o 'redis' con múltiples réplicas."
            )
    else:
        if settings.dev_auth_bypass:
            warnings.append(
                "AVISO: SIREP_DEV_AUTH_BYPASS está activo; toda petición se "
                "atiende con un usuario simulado."
            )

    if settings.max_ingest_files > STARLETTE_DEFAULT_MAX_FILES:
        warnings.append(
            f"AVISO: SIREP_MAX_INGEST_FILES ({settings.max_ingest_files}) supera el "
            f"máximo de partes que el parser multipart acepta por defecto "
            f"({STARLETTE_DEFAULT_MAX_FILES}); las cargas de carpeta se rechazarán "
            "si el cliente no respeta el límite del servidor."
        )
    if settings.max_ingest_total_bytes > settings.org_max_storage_bytes:
        warnings.append(
            "AVISO: SIREP_MAX_INGEST_TOTAL_BYTES supera la cuota de almacenamiento "
            "por organización; las cargas grandes fallarán con 'quota_exceeded'."
        )
    return warnings


def reset_settings_cache() -> None:
    """Uso exclusivo en pruebas para recargar configuración."""
    get_settings.cache_clear()
