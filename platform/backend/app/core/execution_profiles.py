"""Perfiles de ejecución (§14.1).

Define cinco perfiles diferenciados y garantiza que el más permisivo
(``HIGH_RISK_DYNAMIC_ANALYSIS``) nunca se habilite automáticamente: requiere una
bandera explícita de configuración.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.core.config import Settings
from app.core.errors import ForbiddenError


class ExecutionProfile(str, Enum):
    STATIC_ANALYSIS = "STATIC_ANALYSIS"
    CONTROLLED_DEPENDENCY_SETUP = "CONTROLLED_DEPENDENCY_SETUP"
    ISOLATED_TEST_EXECUTION = "ISOLATED_TEST_EXECUTION"
    RESTRICTED_NETWORK_INTEGRATION = "RESTRICTED_NETWORK_INTEGRATION"
    HIGH_RISK_DYNAMIC_ANALYSIS = "HIGH_RISK_DYNAMIC_ANALYSIS"


@dataclass(frozen=True)
class ProfileSpec:
    rank: int
    executes_project_code: bool
    network: str  # none | allowlisted | open
    filesystem: str  # workspace_readonly | workspace_ephemeral | readonly
    isolation: tuple[str, ...]
    description: str


PROFILE_SPECS: dict[ExecutionProfile, ProfileSpec] = {
    ExecutionProfile.STATIC_ANALYSIS: ProfileSpec(
        rank=0,
        executes_project_code=False,
        network="none",
        filesystem="workspace_readonly",
        isolation=("sin ejecución de código del proyecto", "sin red"),
        description="Análisis sin ejecutar el código del proyecto.",
    ),
    ExecutionProfile.CONTROLLED_DEPENDENCY_SETUP: ProfileSpec(
        rank=1,
        executes_project_code=False,
        network="allowlisted",
        filesystem="workspace_ephemeral",
        isolation=("instalación controlada", "red restringida a registros autorizados"),
        description="Preparación controlada de dependencias.",
    ),
    ExecutionProfile.ISOLATED_TEST_EXECUTION: ProfileSpec(
        rank=2,
        executes_project_code=True,
        network="none",
        filesystem="workspace_ephemeral",
        isolation=("proceso sin privilegios", "límites de CPU/memoria/disco", "sin red", "timeout"),
        description="Pruebas locales en un entorno aislado.",
    ),
    ExecutionProfile.RESTRICTED_NETWORK_INTEGRATION: ProfileSpec(
        rank=3,
        executes_project_code=True,
        network="allowlisted",
        filesystem="workspace_ephemeral",
        isolation=("red limitada y autorizada por lista", "límites de recursos"),
        description="Pruebas de integración con acceso de red limitado y autorizado.",
    ),
    ExecutionProfile.HIGH_RISK_DYNAMIC_ANALYSIS: ProfileSpec(
        rank=4,
        executes_project_code=True,
        network="allowlisted",
        filesystem="workspace_ephemeral",
        isolation=(
            "aislamiento reforzado (contenedor/VM)",
            "seccomp/AppArmor cuando esté disponible",
            "sin socket de Docker",
            "sin credenciales del host",
            "limpieza del entorno",
        ),
        description="Análisis dinámico en un entorno reforzado.",
    ),
}

DEFAULT_PROFILE = ExecutionProfile.STATIC_ANALYSIS


def parse_profile(value: str) -> ExecutionProfile:
    try:
        return ExecutionProfile(value)
    except ValueError as error:
        raise ForbiddenError(f"Perfil de ejecución desconocido: {value}.") from error


def is_profile_enabled(profile: ExecutionProfile, settings: Settings) -> bool:
    """Un perfil está habilitado si no supera el perfil activo permitido."""
    if profile is ExecutionProfile.HIGH_RISK_DYNAMIC_ANALYSIS and not settings.execution_allow_high_risk:
        return False
    active = parse_profile(settings.execution_profile)
    return PROFILE_SPECS[profile].rank <= PROFILE_SPECS[active].rank


def active_profile(settings: Settings) -> ExecutionProfile:
    """Perfil de ejecución vigente según la configuración.

    Falla en cerrado: si se configura ``HIGH_RISK_DYNAMIC_ANALYSIS`` sin la
    bandera explícita ``execution_allow_high_risk``, el perfil efectivo degrada
    a ``STATIC_ANALYSIS`` para que el código del proyecto nunca se ejecute.
    """
    profile = parse_profile(settings.execution_profile)
    if (
        profile is ExecutionProfile.HIGH_RISK_DYNAMIC_ANALYSIS
        and not settings.execution_allow_high_risk
    ):
        return DEFAULT_PROFILE
    return profile


def profile_executes_project_code(settings: Settings) -> bool:
    """Indica si el perfil vigente permite ejecutar código del proyecto (§14.1).

    ``STATIC_ANALYSIS`` y ``CONTROLLED_DEPENDENCY_SETUP`` no lo permiten: en
    ellos, cualquier comprobación que requiera ejecutar el código del repositorio
    debe quedar bloqueada y reportarse como tal, nunca como un aprobado.
    """
    return PROFILE_SPECS[active_profile(settings)].executes_project_code


def enabled_profiles(settings: Settings) -> list[str]:
    active = parse_profile(settings.execution_profile)
    active_rank = PROFILE_SPECS[active].rank
    result: list[str] = []
    for profile, spec in PROFILE_SPECS.items():
        if spec.rank > active_rank:
            continue
        if profile is ExecutionProfile.HIGH_RISK_DYNAMIC_ANALYSIS and not settings.execution_allow_high_risk:
            continue
        result.append(profile.value)
    return result


def assert_profile_allowed(profile: ExecutionProfile, settings: Settings) -> None:
    """Falla si se intenta usar un perfil no habilitado (§14.1)."""
    if is_profile_enabled(profile, settings):
        return
    if profile is ExecutionProfile.HIGH_RISK_DYNAMIC_ANALYSIS and not settings.execution_allow_high_risk:
        raise ForbiddenError(
            "El perfil HIGH_RISK_DYNAMIC_ANALYSIS requiere habilitación explícita "
            "(SIREP_EXECUTION_ALLOW_HIGH_RISK); nunca se activa automáticamente."
        )
    raise ForbiddenError(
        f"El perfil {profile.value} supera el perfil activo {settings.execution_profile}."
    )


def current_profile_spec(settings: Settings) -> dict:
    active = parse_profile(settings.execution_profile)
    spec = PROFILE_SPECS[active]
    return {
        "profile": active.value,
        "rank": spec.rank,
        "executes_project_code": spec.executes_project_code,
        "network": spec.network,
        "filesystem": spec.filesystem,
        "isolation": list(spec.isolation),
        "description": spec.description,
        "high_risk_enabled": settings.execution_allow_high_risk,
        "enabled_profiles": enabled_profiles(settings),
    }
