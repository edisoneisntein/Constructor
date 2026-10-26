# Preparación comercial (§21 Fase 12)

Estado de los elementos comerciales del productizado: documentación, despliegue,
gestión de uso y cuotas, costes y facturación. Este documento distingue lo
**implementado** de lo **propuesto**, conforme a §23.

## 1. Resumen de estado

| Elemento (§21 Fase 12) | Estado | Evidencia |
|------------------------|--------|-----------|
| Documentación | `IMPLEMENTED` | `README`, `docs/ARCHITECTURE.md`, `THREAT_MODEL.md`, `LIMITATIONS.md`, `DEPLOYMENT.md`, informes por fase |
| Despliegue | `IMPLEMENTED` | Dockerfiles + `docker-compose.yml`; build/run y worker externo `TEST_PASSED` (`docs/test-runs/20261018-container-e2e.md`, `20261018-external-worker-e2e.md`) |
| Gestión de uso | `IMPLEMENTED` | `usage_records` + `GET /api/v1/observability/usage` + `metric*` |
| Cuotas | `IMPLEMENTED` | `SIREP_ORG_MAX_*` aplicadas en proyecto/ingesta/análisis |
| Costes | `PROPOSED_NOT_IMPLEMENTED` | Sin estimación de coste por IA/tokens (requiere precios de proveedor) |
| Facturación | `PROPOSED_NOT_IMPLEMENTED` | No hay pasarela de pago ni planes |
| Multiusuario | `IMPLEMENTED` | Roles por organización; límites de tasa compartidos en base de datos (`SIREP_RATE_LIMIT_BACKEND=database`) |

## 2. Gestión de uso (implementado)

Cada organización acumula métricas reales en `usage_records`:

- `storage_bytes`: bytes de cada artefacto aceptado.
- `analysis_runs`: un registro por análisis iniciado.
- `files_analyzed`: archivos analizados por análisis completado.

Consulta:

```
GET /api/v1/observability/usage     # uso actual + totales + cuotas y % consumido
GET /api/v1/observability/metrics   # jobs por estado y duración media observable
```

## 3. Cuotas (implementado)

Configurables por entorno; se aplican con `403 quota_exceeded` y detalle
`{resource, used, limit}`:

| Cuota | Variable | Aplica en |
|-------|----------|-----------|
| Proyectos por organización | `SIREP_ORG_MAX_PROJECTS` | crear proyecto |
| Almacenamiento por organización | `SIREP_ORG_MAX_STORAGE_BYTES` | cargar artefacto |
| Análisis concurrentes | `SIREP_ORG_MAX_CONCURRENT_JOBS` | iniciar análisis |

Límites de tasa (`429 rate_limited`, cabecera `Retry-After`):

| Límite | Variable | Ámbito |
|--------|----------|--------|
| API general | `SIREP_RATE_LIMIT_API_PER_MINUTE` | por organización o IP |
| Autenticación | `SIREP_RATE_LIMIT_AUTH_PER_MINUTE` | por IP |

Limitación: implementados **en proceso** (una instancia). Requieren backend
compartido (Redis) para varias instancias.

## 4. Despliegue (parcial)

Ver `docs/DEPLOYMENT.md`. Pendiente verificar la construcción y ejecución real de
las imágenes (`TEST_NOT_RUN`).

## 5. Costes y facturación (propuesto, no implementado)

Para cerrar la Fase 12 en un entorno comercial se requiere, sin inventar cifras:

1. **Modelo de precios**: definir planes y unidades facturables (p. ej. por
   proyecto activo, por uso de análisis, por almacenamiento).
2. **Medición de coste IA**: contabilizar tokens/costes de proveedor por análisis
   (la capa de uso ya persiste eventos; falta el cálculo con tarifas reales).
3. **Facturación**: integración con Stripe/equivalente, plan por organización y
   webhooks de estado de pago.
4. **Cumplimiento**: gestión de IVA/impuestos, facturación electrónica y
   contratos, dependientes de jurisdicción.

Nada de lo anterior está implementado. No debe presentarse como funcionalidad
disponible.

## 6. Riesgos y dependencias

- La facturación depende de decisiones de negocio no especificadas en el PDF.
- La medición de coste IA depende de credenciales y tarifas reales de proveedor
  (§13), hoy `BLOCKED`.
- El escalado (cola externa, Postgres, rate limiting compartido) es requisito
  previo a un servicio multiusuario de producción.
