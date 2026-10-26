"""Limitación de tasa multiusuario (§14, §21 Fase 11/13).

Tres backends intercambiables mediante ``SIREP_RATE_LIMIT_BACKEND``:

* ``memory`` (por defecto): ventana deslizante en memoria del proceso. Solo
  protege una instancia.
* ``database``: contadores en la base de datos (SQLite/PostgreSQL), compartidos
  entre múltiples procesos/instancias que apunten a la misma base. Usa
  ``INSERT ... ON CONFLICT DO UPDATE`` atómico.
* ``redis``: contadores en Redis, ideado para entornos con Redis disponible.
  Proporciona mayor rendimiento y operaciones atómicas nativas.

``check_rate_limit`` y ``reset_rate_limiter`` conservan su contrato.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        if limit <= 0:
            return RateLimitResult(True, 0, 0)
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            timestamps = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(timestamps) >= limit:
                oldest = timestamps[0]
                retry_after = max(1, int(window_seconds - (now - oldest)) + 1)
                self._hits[key] = timestamps
                return RateLimitResult(False, 0, retry_after)
            timestamps.append(now)
            self._hits[key] = timestamps
            return RateLimitResult(True, max(0, limit - len(timestamps)), 0)


class DatabaseRateLimiter:
    """Contador de ventana fija compartido vía base de datos.

    Una sola sentencia ``INSERT ... ON CONFLICT DO UPDATE ... RETURNING`` es
    atómica, por lo que el conteo es correcto aunque varios procesos incrementen
    la misma clave a la vez.
    """

    def __init__(self, database) -> None:  # noqa: ANN001 - evita dependencia circular
        self._database = database

    def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        if limit <= 0:
            return RateLimitResult(True, 0, 0)
        now = time.time()
        window_start = int(now // window_seconds)
        scope = f"{key}:{window_seconds}"
        conn = self._database.connect()
        try:
            with conn:
                row = conn.execute(
                    """
                    INSERT INTO rate_limit_counters(scope_key, window_start, count, updated_at)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(scope_key) DO UPDATE SET
                        count = CASE
                            WHEN rate_limit_counters.window_start = excluded.window_start
                            THEN rate_limit_counters.count + 1 ELSE 1 END,
                        window_start = excluded.window_start,
                        updated_at = excluded.updated_at
                    RETURNING count, window_start
                    """,
                    (scope, window_start, time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(now))),
                ).fetchone()
        finally:
            if not self._database.is_ephemeral:
                conn.close()
        count = int(row["count"])
        if count > limit:
            retry_after = max(1, int((window_start + 1) * window_seconds - now) + 1)
            return RateLimitResult(False, 0, retry_after)
        return RateLimitResult(True, max(0, limit - count), 0)


class RedisRateLimiter:
    """Contador de ventana fija compartido vía Redis.

    Utiliza ``SETNX`` para inicializar la clave y ``EXPIRE`` para que los
    ventanas caduquen automáticamente, sin necesidad de un esquema de tabla
    personalizado. Requiere que Redis esté levantado y accesible.

    La ventana es fija por periodo: cada ``window_seconds`` se reinicia el
    conteo, lo que es suficiente para el uso de rate-limit API y auth.
    """

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        if limit <= 0:
            return RateLimitResult(True, 0, 0)
        redis_key = f"rate_limit:{key}"
        window_start = int(time.time() // window_seconds)
        pipe = self._redis.pipeline()
        try:
            pipe.watch(redis_key)
            current = pipe.get(redis_key)
            if current is None:
                pipe.multi()
                pipe.setex(redis_key, window_seconds, 1)
                count = 1
            else:
                new_count = int(current) + 1
                pipe.multi()
                pipe.expire(redis_key, window_seconds)
                pipe.set(redis_key, new_count)
                count = new_count
            pipe.execute()
        except Exception:
            # Si Redis falla, caemos permitiendo la petición
            return RateLimitResult(True, 0, 0)
        if count > limit:
            retry_after = max(1, window_seconds - int(time.time()) % window_seconds + 1)
            return RateLimitResult(False, 0, retry_after)
        return RateLimitResult(True, max(0, limit - count), 0)


class _InProcessBackend:
    def __init__(self) -> None:
        self._limiter = SlidingWindowLimiter()

    def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitResult:
        return self._limiter.check(key, limit=limit, window_seconds=window_seconds)


_BACKEND: object | None = None


def get_rate_limit_backend():
    global _BACKEND
    if _BACKEND is None:
        from app.core.config import get_settings

        if get_settings().rate_limit_backend == "database":
            from app.db.session import get_database

            _BACKEND = DatabaseRateLimiter(get_database())
        elif get_settings().rate_limit_backend == "redis":
            import redis as redis_module

            _BACKEND = RedisRateLimiter(redis_module.Redis(host=get_settings().redis_host or "localhost",
                                                         port=get_settings().redis_port or 6379,
                                                         decode_responses=True))
        else:
            _BACKEND = _InProcessBackend()
    return _BACKEND


def check_rate_limit(key: str, *, limit: int, window_seconds: int = 60) -> RateLimitResult:
    return get_rate_limit_backend().check(key, limit=limit, window_seconds=window_seconds)


def reset_rate_limiter() -> None:
    """Uso exclusivo en pruebas."""
    global _BACKEND
    _BACKEND = None
