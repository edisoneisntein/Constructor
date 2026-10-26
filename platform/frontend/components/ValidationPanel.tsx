"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getConformanceReport,
  listValidationRequirements,
  runValidation,
  type ConformanceReport,
  type ValidationRequirement,
  type ValidationResult,
  type ValidationRun,
} from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  PASS: "text-emerald-400",
  FAIL: "text-red-400",
  PARTIAL: "text-amber-300",
  BLOCKED: "text-orange-400",
  NOT_RUN: "text-slate-500",
  SKIPPED: "text-amber-300",
  ERROR: "text-red-400",
};

export default function ValidationPanel() {
  const [report, setReport] = useState<ConformanceReport | null>(null);
  const [requirements, setRequirements] = useState<ValidationRequirement[]>([]);
  const [run, setRun] = useState<ValidationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextReport, nextRequirements] = await Promise.all([
        getConformanceReport(),
        listValidationRequirements(),
      ]);
      setReport(nextReport);
      setRequirements(nextRequirements);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function execute() {
    setBusy(true);
    setError(null);
    try {
      setRun(await runValidation());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  const titles = new Map(requirements.map((item) => [item.id, item.title]));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-slate-300">
          Validador de implementación · conformidad con el requisito
        </h3>
        <button className="btn" onClick={execute} disabled={busy}>
          {busy ? "Validando…" : "Ejecutar validación"}
        </button>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      {report && (
        <div className="rounded border border-slate-800 p-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-400">
            <span>
              Conformidad:{" "}
              <span className="font-medium text-slate-200">
                {(report.conformance_ratio * 100).toFixed(1)}%
              </span>{" "}
              ({report.verified}/{report.total})
            </span>
            <span className={STATUS_STYLES.FAIL}>Fallos: {report.failed}</span>
            <span className={STATUS_STYLES.PARTIAL}>Parciales: {report.partial}</span>
            <span className={STATUS_STYLES.BLOCKED}>Bloqueados: {report.blocked}</span>
            <span className={STATUS_STYLES.NOT_RUN}>Sin ejecutar: {report.not_run}</span>
          </div>

          <table className="mt-3 w-full text-left text-xs">
            <thead className="text-slate-500">
              <tr>
                <th className="py-1">Requisito</th>
                <th className="py-1">Sección</th>
                <th className="py-1">Estado</th>
                <th className="py-1">Comprob.</th>
                <th className="py-1">Validado</th>
              </tr>
            </thead>
            <tbody>
              {report.items.map((item) => (
                <tr key={item.id} className="border-t border-slate-800">
                  <td className="py-1">
                    <span className="font-mono text-slate-400">{item.id}</span> · {item.title}
                  </td>
                  <td className="py-1 text-slate-500">{item.source_section ?? "—"}</td>
                  <td className={`py-1 font-medium ${STATUS_STYLES[item.status] ?? ""}`}>{item.status}</td>
                  <td className="py-1 text-slate-400">
                    {item.checks_passed}/{item.checks_total}
                    {item.checks_failed ? ` · ${item.checks_failed} fallo(s)` : ""}
                    {item.checks_skipped ? ` · ${item.checks_skipped} omitida(s)` : ""}
                  </td>
                  <td className="py-1 text-slate-500">{item.validated_at ? item.validated_at.slice(0, 19) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {run && (
        <div className="space-y-3 rounded border border-slate-800 p-3">
          <p className="text-xs text-slate-400">
            Ejecución <span className="font-mono">{run.id}</span> · hash{" "}
            <span className="font-mono">{run.code_hash?.slice(0, 12)}</span> · {run.duration_ms} ms · resultados
            sobre la versión actual del código.
          </p>
          {run.limitations.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-amber-300">
              {run.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          {run.results.map((result) => (
            <ResultView key={result.id} result={result} title={titles.get(result.requirement_id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function ResultView({ result, title }: { result: ValidationResult; title?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded border border-slate-800">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left text-xs"
        onClick={() => setOpen((value) => !value)}
      >
        <span>
          <span className="font-mono text-slate-400">{result.requirement_id}</span>{" "}
          {title ? `· ${title}` : ""}
        </span>
        <span className={`font-medium ${STATUS_STYLES[result.status] ?? ""}`}>{result.status}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-800 px-3 py-2">
          {result.evidence.map((item) => (
            <div key={item.id} className="text-xs">
              <div className="flex items-center justify-between">
                <span>
                  <span className="font-mono text-slate-500">{item.check_id}</span> [{item.check_type}]{" "}
                  {item.criterion}
                </span>
                <span className={STATUS_STYLES[item.status] ?? ""}>{item.status}</span>
              </div>
              {item.command && (
                <pre className="mt-1 overflow-x-auto text-slate-500">{item.command}</pre>
              )}
              {item.output && (
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-slate-500">
                  {item.output}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
