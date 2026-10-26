"""Proceso trabajador de la cola externa (§4.3, §21 Fase 13).

Ejecuta análisis encolados en ``analysis_jobs`` cuando la API corre con
``SIREP_JOB_QUEUE=external``. Permite escalar horizontalmente: N workers sobre la
misma base de datos reclaman trabajos de forma atómica (``claim_next_job``) y la
cancelación sigue siendo cooperativa leyendo ``cancel_requested`` de la base.

Uso:
    SIREP_JOB_QUEUE=external python -m app.worker
    SIREP_JOB_QUEUE=external python -m app.worker --once   # procesa lo encolado y sale
"""

from __future__ import annotations

import argparse
import signal
import sqlite3
import threading
import time

from app.core.config import Settings, get_settings
from app.core.ids import new_id, utcnow_iso
from app.core.logging import configure_logging, get_logger
from app.db import repositories as repo
from app.db.session import get_database, initialize_database
from app.services.analysis_service import purge_expired_artifacts, run_analysis_job

_logger = get_logger("worker")


class Worker:
    def __init__(self, settings: Settings, *, worker_id: str | None = None) -> None:
        self._settings = settings
        self.worker_id = worker_id or settings.worker_id or new_id("wrk")
        self._stop = threading.Event()
        self._last_purge = 0.0

    # -- ciclo de vida -----------------------------------------------------
    def request_stop(self, *_: object) -> None:
        _logger.info("worker_stop_requested", extra={"worker_id": self.worker_id})
        self._stop.set()

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)

    # -- procesamiento -----------------------------------------------------
    def recover(self, conn: sqlite3.Connection) -> dict[str, int]:
        result = repo.recover_stale_jobs(
            conn,
            now=utcnow_iso(),
            stale_seconds=self._settings.job_stale_after_seconds,
            max_attempts=self._settings.job_max_attempts,
        )
        conn.commit()
        if result["requeued"] or result["failed"]:
            _logger.info("worker_recovered", extra={"worker_id": self.worker_id, **result})
        return result

    def maybe_purge(self, conn: sqlite3.Connection) -> int:
        """Aplica la retención de artefactos si venció el intervalo (§14.6)."""

        interval = self._settings.retention_purge_interval_seconds
        if interval <= 0:
            return 0
        now = time.monotonic()
        if self._last_purge and now - self._last_purge < interval:
            return 0
        self._last_purge = now
        purged = purge_expired_artifacts(conn, self._settings)
        conn.commit()
        if purged:
            _logger.info(
                "worker_retention_purge",
                extra={"worker_id": self.worker_id, "count": len(purged)},
            )
        return len(purged)

    def run_once(self) -> bool:
        """Reclama y ejecuta un trabajo. Devuelve ``True`` si procesó alguno."""

        database = initialize_database()
        conn = database.connect()
        try:
            self.maybe_purge(conn)
            self.recover(conn)
            job = repo.claim_next_job(conn, worker_id=self.worker_id, now=utcnow_iso())
            conn.commit()
            if job is None:
                return False
            if repo.is_cancel_requested(conn, job["id"]):
                repo.update_job(
                    conn, job["id"], status="CANCELLED", phase="cancelled", finished_at=utcnow_iso()
                )
                conn.commit()
                return True
            _logger.info(
                "worker_claimed",
                extra={"worker_id": self.worker_id, "job_id": job["id"], "attempt": job["attempt_count"]},
            )
            run_analysis_job(
                job_id=job["id"],
                project_id=job["project_id"],
                organization_id=job["organization_id"],
                artifact_id=job["artifact_id"],
                deep_analysis=False,
                is_cancelled=lambda: _db_cancel_check(job["id"]),
                settings=self._settings,
                worker_id=self.worker_id,
            )
            return True
        except Exception:  # noqa: BLE001
            _logger.exception("worker_job_error", extra={"worker_id": self.worker_id})
            return True
        finally:
            if not database.is_ephemeral:
                conn.close()

    def run_forever(self) -> None:
        self.install_signal_handlers()
        _logger.info("worker_started", extra={"worker_id": self.worker_id, "queue": self._settings.job_queue_backend})
        while not self._stop.is_set():
            processed = self.run_once()
            if not processed:
                time.sleep(self._settings.worker_poll_interval_seconds)
        _logger.info("worker_stopped", extra={"worker_id": self.worker_id})


def _db_cancel_check(job_id: str) -> bool:
    """Comprobación de cancelación cooperativa entre procesos (§4.3)."""

    database = get_database()
    conn = database.connect()
    try:
        return repo.is_cancel_requested(conn, job_id)
    finally:
        if not database.is_ephemeral:
            conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trabajador de la cola externa SIREP.")
    parser.add_argument("--once", action="store_true", help="Procesa lo encolado y termina.")
    args = parser.parse_args(argv)

    configure_logging()
    settings = get_settings()
    worker = Worker(settings)
    if settings.job_queue_backend != "external":
        _logger.warning(
            "worker_queue_not_external",
            extra={"worker_id": worker.worker_id, "queue": settings.job_queue_backend},
        )
    if args.once:
        while worker.run_once():
            pass
        return 0
    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
