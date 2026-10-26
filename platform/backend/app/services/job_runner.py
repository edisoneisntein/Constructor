"""Ejecutor de trabajos asíncronos en proceso (§4.3, MVP).

El PDF permite elegir la tecnología de colas "después de evaluar las necesidades
reales". Para el MVP se usa un pool de hilos con:
  * estado persistido en la base de datos;
  * cancelación cooperativa real (no simulada);
  * límite de concurrencia;
  * registro de errores.

En la Fase 11 se sustituye por Celery/ARQ + Redis sin cambiar los contratos.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from app.core.logging import get_logger

JobCallable = Callable[[Callable[[], bool]], None]


class JobRunner:
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sirep-job")
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()
        self._logger = get_logger("job_runner")

    def submit(self, job_id: str, task: JobCallable) -> None:
        self._executor.submit(self._run, job_id, task)

    def _run(self, job_id: str, task: JobCallable) -> None:
        try:
            task(lambda: self.is_cancelled(job_id))
        except Exception:  # noqa: BLE001 - se registra y el estado se marca en la tarea
            self._logger.exception("job_error", extra={"job_id": job_id})
        finally:
            self.clear(job_id)

    def request_cancel(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.add(job_id)

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancelled

    def clear(self, job_id: str) -> None:
        with self._lock:
            self._cancelled.discard(job_id)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


_runner: JobRunner | None = None


def get_job_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner


def reset_job_runner() -> None:
    """Uso exclusivo en pruebas."""
    global _runner
    if _runner is not None:
        _runner.shutdown()
    _runner = None
