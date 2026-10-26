# Modelo de amenazas (§19.3)

## Activos

Código fuente del cliente, credenciales de análisis, resultados de análisis,
metadatos de organizaciones y usuarios.

## Amenazas y mitigaciones

| Amenaza | Vector | Mitigación implementada |
| --- | --- | --- |
| Path traversal (zip-slip) | Entrada ZIP con `../` o rutas absolutas | `safe_zip` normaliza y rechaza rutas fuera del destino |
| Symlinks maliciosos | Entrada ZIP con enlaces simbólicos | Se rechazan entradas con bit `S_IFLNK` |
| Zip bomb | Alta ratio de compresión / tamaño total | Límites de ratio, tamaño por archivo, tamaño total y nº de entradas |
| Ejecución durante el análisis | Código del cliente | Solo **análisis estático**; nunca se ejecuta el código analizado |
| Fuga entre organizaciones (IDOR) | Acceso a recursos ajenos | Scoping por `organization_id` en cada consulta; 404 si no pertenece |
| Escalada de privilegios | Roles | Ranking `viewer < developer < owner < admin`; acciones sensibles requieren rol |
| Fuerza bruta de sesión/token | Endpoints de auth | Tokens opacos de 256 bits, PBKDF2-HMAC-SHA256, comparación en tiempo constante |
| DoS por archivos grandes | Cargas | Límite de tamaño de carga y de extracción; timeouts en subproceso Node |
| Fuga de secretos en logs | Logs | Redacción multicanal en `core/logging.py`: claves API (Google/NVIDIA/AWS/GitHub/Slack), `Bearer`, JWT, claves privadas PEM y `private_key` de cuentas de servicio (§14.6) |
| Bloqueo del servidor | Análisis largos | Ejecución en segundo plano, cancelación cooperativa, timeouts |
| Abuso de recursos por subprocesos | Herramientas externas (REA, bridge Node) | Límites `RLIMIT_CPU`/`RLIMIT_FSIZE`/`RLIMIT_NOFILE` vía `preexec_fn` (`core/sandbox.py`, §14.2) |
| SSRF / acceso a red interna | Conexiones salientes a proveedores | `core/net_guard.py` bloquea loopback, rangos privados y metadatos (169.254.169.254) y exige lista de hosts autorizados (§14.4) |
| Escalada a ejecución dinámica | Aumento silencioso de capacidades | Perfiles de ejecución (`core/execution_profiles.py`); `HIGH_RISK_DYNAMIC_ANALYSIS` requiere bandera explícita y nunca se activa solo (§14.1) |
| Retención indebida de código | Artefactos persistentes | Borrado explícito (`DELETE .../artifacts/{id}`) y purga por retención con baja lógica y auditoría (§14.6) |
| Abuso de recursos (DoS lógico) | Uso masivo por usuario/organización | Cuotas por organización (`403 quota_exceeded`) y límite de tasa con `429 rate_limited` + `Retry-After` (`core/rate_limit.py`, `core/observability.py`) |
| Falta de trazabilidad operativa | Diagnóstico de incidentes | Correlación `X-Request-ID`, log estructurado por petición, `/health` y `/health/ready` (`core/observability.py`) |

## Perfiles de ejecución (§14.1)

| Perfil | Ejecuta código | Red | Aislamiento |
| --- | --- | --- | --- |
| `STATIC_ANALYSIS` (por defecto) | No | Ninguna | Sin ejecución |
| `CONTROLLED_DEPENDENCY_SETUP` | No | Lista blanca | Instalación controlada |
| `ISOLATED_TEST_EXECUTION` | Sí | Ninguna | Sin privilegios, límites, timeout |
| `RESTRICTED_NETWORK_INTEGRATION` | Sí | Lista blanca | Límites + red limitada |
| `HIGH_RISK_DYNAMIC_ANALYSIS` | Sí | Lista blanca | Refuerzo (contenedor/VM), requiere habilitación explícita |

## Fuera de alcance (fase actual)

- Ejecución dinámica real del código del cliente en contenedor/VM aislado (los
  perfiles y límites existen como control; no hay motor que ejecute código aún).
- Limitación de tasa **distribuida** y WAF: existe un limitador en proceso
  (`core/rate_limit.py`), válido para una sola instancia; para varias instancias se
  requiere un backend compartido (Redis).
- Cifrado en reposo gestionado por KMS (pendiente de entorno de despliegue).
- El guard de red valida el host literal y la lista blanca; **no resuelve DNS por
  defecto**, por lo que un nombre que resuelva a una IP interna no se detecta
  salvo que se invoque con `resolve=True` (riesgo de DNS rebinding documentado).
