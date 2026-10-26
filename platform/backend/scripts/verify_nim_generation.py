"""Verificación en vivo de la generación de código con NIM (§10).

Ejecuta el ciclo completo contra una API en marcha (local o contenedor):

    register → project → artifact → analysis → generation (NIM)
    → verificación de sintaxis → aprobar → aplicar → validar

Uso:
    SIREP_API_BASE_URL=http://127.0.0.1:8000 python -m scripts.verify_nim_generation
"""

from __future__ import annotations

import io
import os
import sys
import time
import zipfile

import httpx

BASE_URL = os.environ.get("SIREP_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

SAMPLE_FILES = {
    "src/math_utils.py": "def add(a, b):\n    return a - b\n",
    "README.md": "# demo\n",
}


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in SAMPLE_FILES.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def main() -> int:
    stamp = int(time.time())
    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        session = client.post(
            "/api/v1/auth/register",
            json={
                "email": f"nimgen+{stamp}@example.com",
                "password": "supersecret123",
                "display_name": f"nimgen{stamp}",
                "organization_name": f"NimGen {stamp}",
            },
        )
        session.raise_for_status()
        token = session.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        orgs = client.get("/api/v1/organizations", headers=headers).json()
        org_id = orgs[0]["id"]
        headers["X-Organization-Id"] = org_id

        project = client.post("/api/v1/projects", json={"name": "NIM Gen"}, headers=headers)
        project.raise_for_status()
        project_id = project.json()["id"]

        upload = client.post(
            f"/api/v1/projects/{project_id}/artifacts",
            files={"file": ("demo.zip", _zip_bytes(), "application/zip")},
            headers=headers,
        )
        upload.raise_for_status()
        artifact_id = upload.json()["id"]

        started = client.post(
            f"/api/v1/projects/{project_id}/analyses",
            json={"artifact_id": artifact_id},
            headers=headers,
        )
        started.raise_for_status()
        analysis_id = started.json()["id"]

        deadline = time.time() + 120
        status = "PENDING"
        while time.time() < deadline:
            summary = client.get(f"/api/v1/analyses/{analysis_id}", headers=headers).json()
            status = summary["job"]["status"]
            if status in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS", "FAILED", "CANCELLED"}:
                break
            time.sleep(0.5)
        print(f"analysis status: {status}")
        if status not in {"COMPLETED", "COMPLETED_WITH_LIMITATIONS"}:
            print("FAIL: el análisis no completó.")
            return 1

        response = client.post(
            f"/api/v1/analyses/{analysis_id}/generations",
            json={
                "instruction": (
                    "Corrige el error en src/math_utils.py: la función add debe sumar "
                    "en lugar de restar."
                ),
                "target_path": "src/math_utils.py",
                "mode": "repair",
                "ai_consent": True,
            },
            headers=headers,
        )
        print(f"generation status: {response.status_code}")
        if response.status_code != 201:
            print(response.text)
            return 1
        body = response.json()
        change = body["change_set"]
        print(f"model: {body['model']}  mode: {body['mode']}  latency_ms: {body['latency_ms']}")
        print(f"summary: {body['summary']}")
        print(f"limitations: {body['limitations']}")
        for item in body["verification"]:
            print(
                f"  - {item['path']} [{item['language']}] {item['change_type']} "
                f"syntax_checked={item['syntax_checked']} syntax_ok={item['syntax_ok']} "
                f"+{item['additions']}/-{item['deletions']}"
            )
        for file in change["files"]:
            print("--- diff ---")
            print(file["unified_diff"])

        if not all(item["syntax_ok"] is True for item in body["verification"] if item["syntax_checked"]):
            print("FAIL: la verificación de sintaxis no pasó.")
            return 1

        change_id = change["id"]
        for action in ("approve", "apply", "validate"):
            payload = {"decision": "approved"} if action == "approve" else None
            step = client.post(
                f"/api/v1/change-sets/{change_id}/{action}", json=payload, headers=headers
            )
            print(f"{action}: {step.status_code}")
            if step.status_code != 200:
                print(step.text)
                return 1

        final = client.get(f"/api/v1/change-sets/{change_id}", headers=headers).json()
        print(f"final status: {final['status']}")
        print(f"validation_result: {final['validation_result']}")
        print("RESULT: TEST_PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
