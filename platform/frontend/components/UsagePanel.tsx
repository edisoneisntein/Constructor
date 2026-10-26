"use client";

import { useEffect, useState } from "react";
import { getMetrics, getUsage, type Metrics, type Usage } from "@/lib/api";

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let size = value / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(1)} ${units[index]}`;
}

export default function UsagePanel({ refreshKey }: { refreshKey?: string }) {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([getUsage(), getMetrics()])
      .then(([u, m]) => {
        if (!active) return;
        setUsage(u);
        setMetrics(m);
      })
      .catch((err) => active && setError(err instanceof Error ? err.message : "Error"));
    return () => {
      active = false;
    };
  }, [refreshKey]);

  if (error) return <p className="text-sm text-red-400">{error}</p>;
  if (!usage || !metrics) return <p className="text-sm text-slate-500">Cargando uso…</p>;

  return (
    <div className="card space-y-4">
      <div>
        <h2 className="text-sm font-medium text-slate-300">Uso de la organización</h2>
        <div className="mt-2 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <Metric label="Proyectos" value={String(usage.projects)} />
          <Metric label="Artefactos" value={String(usage.artifacts)} />
          <Metric label="Almacenamiento" value={formatBytes(usage.storage_bytes)} />
          <Metric label="Hallazgos" value={String(usage.findings)} />
          <Metric label="Jobs activos" value={String(usage.active_jobs)} />
          <Metric label="Jobs totales" value={String(metrics.jobs_total)} />
          <Metric label="Jobs finalizados" value={String(metrics.jobs_finished)} />
          <Metric
            label="Duración media"
            value={metrics.avg_duration_seconds !== null ? `${metrics.avg_duration_seconds}s` : "n/d"}
          />
        </div>
      </div>

      <div>
        <p className="mb-1 text-xs uppercase text-slate-500">Cuotas</p>
        <ul className="space-y-2 text-xs">
          {Object.entries(usage.quotas).map(([key, quota]) => (
            <li key={key}>
              <div className="flex items-center justify-between text-slate-400">
                <span>{key}</span>
                <span>
                  {quota.limit > 0 ? `${quota.used} / ${quota.limit}` : `${quota.used} (sin límite)`}
                </span>
              </div>
              {quota.limit > 0 && quota.percent !== null && (
                <div className="mt-1 h-1.5 w-full rounded bg-slate-800">
                  <div
                    className={`h-1.5 rounded ${quota.percent >= 90 ? "bg-red-500" : quota.percent >= 70 ? "bg-amber-500" : "bg-sky-600"}`}
                    style={{ width: `${Math.min(quota.percent, 100)}%` }}
                  />
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div>
        <p className="mb-1 text-xs uppercase text-slate-500">Jobs por estado</p>
        <div className="flex flex-wrap gap-2 text-xs">
          {Object.entries(metrics.jobs_by_status).map(([status, count]) => (
            <span key={status} className="rounded bg-slate-800 px-2 py-0.5 text-slate-300">
              {status}: {count}
            </span>
          ))}
          {Object.keys(metrics.jobs_by_status).length === 0 && (
            <span className="text-slate-600">Sin jobs registrados.</span>
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-800 px-3 py-2">
      <p className="text-slate-500">{label}</p>
      <p className="font-medium text-slate-200">{value}</p>
    </div>
  );
}
