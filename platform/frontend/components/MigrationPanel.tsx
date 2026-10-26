"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createMigrationPlan,
  getMigrationPlan,
  listMigrationPlans,
  type CompatibilityAssessment,
  type MigrationChange,
  type MigrationPlan,
  type MigrationPlanDetail,
} from "@/lib/api";

const categoryStyles: Record<string, string> = {
  DIRECTLY_COMPATIBLE: "bg-emerald-900/60 text-emerald-200",
  COMPATIBLE_WITH_ADAPTER: "bg-sky-900/60 text-sky-200",
  PARTIAL_COMPATIBILITY: "bg-amber-900/60 text-amber-200",
  REQUIRES_REDESIGN: "bg-orange-900/60 text-orange-200",
  UNSUPPORTED: "bg-red-900/60 text-red-200",
  NOT_VERIFIED: "bg-slate-800 text-slate-300",
};

export default function MigrationPanel({
  projectId,
  analysisId,
}: {
  projectId: string;
  analysisId: string;
}) {
  const [plans, setPlans] = useState<MigrationPlan[]>([]);
  const [detail, setDetail] = useState<MigrationPlanDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const list = await listMigrationPlans(projectId);
    setPlans(list);
    return list;
  }, [projectId]);

  useEffect(() => {
    setDetail(null);
    setPlans([]);
    refresh().catch((err) => setError(err instanceof Error ? err.message : "Error"));
  }, [refresh]);

  async function createPlan() {
    setBusy(true);
    setError(null);
    try {
      const plan = await createMigrationPlan(projectId, analysisId);
      setDetail(plan);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function openPlan(id: string) {
    setError(null);
    try {
      setDetail(await getMigrationPlan(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Centro de migraciones (Gemini → NVIDIA NIM)</h3>
        <button className="btn" onClick={createPlan} disabled={busy}>
          Analizar migración
        </button>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <ul className="space-y-2">
        {plans.map((plan) => (
          <li
            key={plan.id}
            className={`cursor-pointer rounded border px-3 py-2 text-sm ${
              detail?.id === plan.id ? "border-sky-600 bg-slate-800/60" : "border-slate-800"
            }`}
            onClick={() => openPlan(plan.id)}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs">{plan.id}</span>
              <span className="text-xs text-slate-400">
                {plan.source_provider} → {plan.target_provider} · {plan.operation_count} operaciones
              </span>
            </div>
          </li>
        ))}
        {plans.length === 0 && <li className="text-sm text-slate-500">Sin planes de migración.</li>}
      </ul>

      {detail && <MigrationDetail detail={detail} />}
    </div>
  );
}

function MigrationDetail({ detail }: { detail: MigrationPlanDetail }) {
  const matrix = detail.plan?.compatibility_matrix ?? [];
  const operations = detail.plan?.operations ?? [];
  const changes = detail.plan?.changes ?? detail.changes;
  const limitations = detail.plan?.limitations ?? detail.limitations ?? [];
  const sources = detail.plan?.sources ?? detail.sources ?? [];
  const summary = detail.matrix_summary ?? {};

  return (
    <div className="space-y-4 rounded border border-slate-800 p-3">
      <div className="text-xs text-slate-400">
        <p>
          Destino: <span className="font-mono">{detail.target_base_url}</span> · modelo{" "}
          <span className="font-mono">{detail.target_model}</span>
        </p>
        <p>Fuentes verificadas: {detail.verified_at}</p>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        {Object.entries(summary).map(([category, count]) => (
          <span key={category} className={`rounded px-2 py-0.5 ${categoryStyles[category] ?? "bg-slate-800"}`}>
            {category}: {count}
          </span>
        ))}
      </div>

      <div>
        <p className="mb-1 text-xs uppercase text-slate-500">Matriz de compatibilidad</p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="px-2 py-1">Operación</th>
                <th className="px-2 py-1">Categoría</th>
                <th className="px-2 py-1">Protocolo</th>
                <th className="px-2 py-1">Equivalencia</th>
                <th className="px-2 py-1">Endpoint destino</th>
              </tr>
            </thead>
            <tbody>
              {matrix.map((assessment: CompatibilityAssessment) => (
                <tr key={assessment.operation_kind} className="border-t border-slate-800">
                  <td className="px-2 py-1 font-mono">{assessment.operation_kind}</td>
                  <td className="px-2 py-1">
                    <span className={`rounded px-1.5 py-0.5 ${categoryStyles[assessment.category] ?? "bg-slate-800"}`}>
                      {assessment.category}
                    </span>
                  </td>
                  <td className="px-2 py-1">{assessment.protocol_compatibility}</td>
                  <td className="px-2 py-1">{assessment.functional_equivalence}</td>
                  <td className="px-2 py-1 font-mono text-slate-400">{assessment.target_endpoint}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <p className="mb-1 text-xs uppercase text-slate-500">Operaciones detectadas ({operations.length})</p>
        <ul className="space-y-1 text-xs text-slate-400">
          {operations.map((operation, index) => (
            <li key={index} className="font-mono">
              [{operation.kind}] {operation.file_path}:{operation.line}
              {operation.model ? ` · ${operation.model}` : ""}
            </li>
          ))}
          {operations.length === 0 && <li className="text-slate-600">No se detectaron integraciones de Gemini.</li>}
        </ul>
      </div>

      <div className="space-y-2">
        <p className="text-xs uppercase text-slate-500">Cambios propuestos ({changes.length})</p>
        {changes.map((change: MigrationChange) => (
          <div key={change.id ?? change.change_ref} className="rounded border border-slate-800">
            <div className="flex items-center justify-between border-b border-slate-800 px-3 py-1 text-xs">
              <span>
                {change.description}
              </span>
              <span className="text-slate-500">
                {change.kind} · {change.action} · {change.reversible ? "reversible" : "no reversible"}
              </span>
            </div>
            {change.diff && (
              <pre className="overflow-x-auto p-2 text-xs">
                {change.diff.split("\n").map((line, index) => {
                  const color = line.startsWith("+")
                    ? "text-emerald-400"
                    : line.startsWith("-")
                      ? "text-red-400"
                      : line.startsWith("@@")
                        ? "text-sky-400"
                        : "text-slate-400";
                  return (
                    <div key={index} className={color}>
                      {line || " "}
                    </div>
                  );
                })}
              </pre>
            )}
          </div>
        ))}
      </div>

      <div>
        <p className="mb-1 text-xs uppercase text-slate-500">Limitaciones</p>
        <ul className="list-disc space-y-1 pl-5 text-xs text-amber-300/80">
          {limitations.map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      </div>

      <div>
        <p className="mb-1 text-xs uppercase text-slate-500">Fuentes</p>
        <ul className="space-y-1 text-xs text-slate-400">
          {sources.map((source, index) => (
            <li key={index}>
              <a href={source.url} target="_blank" rel="noreferrer" className="text-sky-400 underline">
                {source.name}
              </a>{" "}
              ({source.verified_at})
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
