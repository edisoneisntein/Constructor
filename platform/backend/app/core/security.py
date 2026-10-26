"""Primitivas de seguridad.

§16/§14: autenticación y autorización. No se implementa criptografía propia:
se usan primitivas estándar (PBKDF2-HMAC-SHA256 vía hashlib, tokens opacos
generados con secrets y comparados en tiempo constante con hmac.compare_digest).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 240_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Devuelve 'pbkdf2_sha256$iteraciones$salt_hex$hash_hex'."""
    if not isinstance(password, str) or password == "":
        raise ValueError("password vacío")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Verifica una contraseña contra el hash almacenado en tiempo constante."""
    if not password or not encoded:
        return False
    try:
        algorithm, iterations_raw, salt_hex, digest_hex = encoded.split("$")
    except ValueError:
        return False
    if algorithm != PBKDF2_ALGORITHM:
        return False
    try:
        iterations = int(iterations_raw)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


def generate_session_token() -> tuple[str, str]:
    """Crea un token de sesión opaco.

    Devuelve (token_en_claro, token_hash). Solo el hash se persiste (§14.6).
    El token en claro se entrega una única vez al cliente.
    """
    raw = secrets.token_urlsafe(32)
    return raw, hash_session_token(raw)


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
