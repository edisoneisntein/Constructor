"""Control de red y defensa contra SSRF (§14.4).

Restringe las conexiones salientes: solo se permiten esquemas http/https y hosts
externos autorizados; se bloquean direcciones internas, de loopback, de enlace
local, rangos privados y la dirección de metadatos cloud.

Limitación honesta: no se resuelve DNS por defecto (evita depender de la red);
por tanto la protección se basa en el host literal y en la lista de autorizados.
Para despliegues que resuelvan nombres dinámicos debe habilitarse
``resolve=True`` y combinarse con un proxy de salida.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from app.core.errors import ForbiddenError

ALLOWED_SCHEMES = {"http", "https"}

_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
}

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local + metadatos
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),  # ULA
    ipaddress.ip_network("fe80::/10"),  # link-local IPv6
]


def _is_blocked_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(address in network for network in _BLOCKED_NETWORKS)


def is_host_allowed(host: str, allowlist: list[str] | None = None) -> bool:
    lowered = (host or "").lower().strip(".")
    if not lowered:
        return False
    if lowered in _BLOCKED_HOSTNAMES or lowered.endswith(".localhost") or lowered.endswith(".internal"):
        return False
    if _is_blocked_ip(lowered):
        return False
    if allowlist:
        normalized = {item.lower().strip(".") for item in allowlist if item}
        if normalized and lowered not in normalized:
            return False
    return True


def validate_outbound_url(
    url: str,
    *,
    allowlist: list[str] | None = None,
    resolve: bool = False,
) -> None:
    """Falla con ``ForbiddenError`` si la URL no es un destino saliente permitido."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ForbiddenError(
            f"Esquema no permitido para conexión saliente: '{parsed.scheme or '(vacío)'}'."
        )
    host = parsed.hostname or ""
    if not is_host_allowed(host, allowlist):
        raise ForbiddenError(f"Host de destino no autorizado: '{host}'.")
    if resolve:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except socket.gaierror as error:
            raise ForbiddenError(f"No se pudo resolver el host '{host}'.") from error
        for info in infos:
            resolved = info[4][0]
            if _is_blocked_ip(resolved):
                raise ForbiddenError(
                    f"El host '{host}' resuelve a una dirección interna bloqueada ({resolved})."
                )
