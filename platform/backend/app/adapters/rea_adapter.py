"""Adaptador REA desacoplado (§3.3).

REA no es dependencia rígida: se invoca como **proceso externo** mediante su CLI
público (``rea ... --json``). Responsabilidades verificables:
  * localizar el ejecutable y comprobar versión/requisitos;
  * invocar solo operaciones estáticas permitidas (allowlist);
  * aplicar límites de tiempo;
  * capturar y normalizar errores sin que se propaguen al núcleo SaaS;
  * normalizar la salida (NDJSON + Evidence) a un contrato interno.

Si REA no está disponible, el flujo vertical continúa y el análisis profundo se
marca como no disponible (§1.4).
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Allowlist: en el MVP solo se permite análisis estático (sin lanzar GUI ni proveedores nativos).
ALLOWED_OPERATIONS = {"analyze-javascript-application"}


@dataclass
class ReaOutcome:
    available: bool
    reason: str | None = None
    evidence_id: str | None = None
    subject_sha256: str | None = None
    provider: str | None = None
    files_projected: int | None = None
    operation: str | None = None


@dataclass
class ReaStatus:
    available: bool
    binary: str | None
    version: str | None
    reason: str | None = None


class REAAdapter:
    def __init__(
        self,
        binary: str | None = None,
        *,
        enabled: bool = True,
        timeout_seconds: int = 180,
        limits: dict | None = None,
    ) -> None:
        self._configured_binary = binary
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self._limits = limits or {}
        self._resolved: str | None = binary

    # -- discovery ---------------------------------------------------------
    def find_binary(self) -> str | None:
        if self._configured_binary and Path(self._configured_binary).exists():
            return self._configured_binary
        for name in ("rea", "rea-agents"):
            found = shutil.which(name)
            if found:
                return found
        candidates = sorted(glob.glob(str(Path.home() / ".npm/_npx/*/node_modules/rea-agents/scripts/rea.mjs")))
        if candidates:
            return candidates[0]
        return None

    def _node(self) -> str | None:
        return shutil.which("node")

    def status(self) -> ReaStatus:
        if not self.enabled:
            return ReaStatus(False, None, None, "El adaptador REA está deshabilitado por configuración.")
        binary = self.find_binary()
        if not binary:
            return ReaStatus(False, None, None, "No se localizó el ejecutable de REA.")
        if self._node() is None:
            return ReaStatus(False, binary, None, "Node.js no está disponible para ejecutar REA.")
        version = self._run_version(binary)
        return ReaStatus(True, binary, version, None)

    def _run_version(self, binary: str) -> str | None:
        try:
            completed = subprocess.run(
                [self._node() or "node", binary, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        return completed.stdout.strip() or None

    # -- operations --------------------------------------------------------
    def analyze_javascript_application(self, root: Path) -> ReaOutcome:
        if not self.enabled:
            return ReaOutcome(False, "El adaptador REA está deshabilitado.")
        binary = self.find_binary()
        node = self._node()
        if not binary or not node:
            return ReaOutcome(False, "REA o Node.js no disponibles.")
        command = [node, binary, "analyze-javascript-application", str(root), "--json"]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                **self._limits,
            )
        except subprocess.TimeoutExpired:
            return ReaOutcome(False, "REA excedió el tiempo límite.")
        except OSError as error:
            return ReaOutcome(False, f"No se pudo iniciar REA: {error}.")
        if completed.returncode != 0:
            return ReaOutcome(False, f"REA terminó con código {completed.returncode}.")
        payload = self._last_json_object(completed.stdout)
        if payload is None:
            return ReaOutcome(False, "REA no devolvió un objeto JSON final.")
        subject = payload.get("subject") or {}
        digest = (subject.get("digest") or {}).get("sha256")
        normalized = payload.get("normalized_result") or {}
        projected = None
        if isinstance(normalized, dict):
            files = normalized.get("files")
            if isinstance(files, list):
                projected = len(files)
        return ReaOutcome(
            available=True,
            evidence_id=payload.get("evidence_id"),
            subject_sha256=digest,
            provider=(payload.get("provider") or {}).get("id"),
            files_projected=projected,
            operation=payload.get("operation"),
        )

    @staticmethod
    def _last_json_object(stdout: str) -> dict | None:
        for line in reversed([line for line in stdout.splitlines() if line.strip()]):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "evidence_id" in value:
                return value
        return None


def build_rea_adapter(
    binary: str | None, *, enabled: bool, timeout_seconds: int, limits: dict | None = None
) -> REAAdapter:
    return REAAdapter(binary, enabled=enabled, timeout_seconds=timeout_seconds, limits=limits)


def rea_env_hint() -> str:
    return os.environ.get("SIREP_REA_BINARY", "")
