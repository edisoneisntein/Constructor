"use client";

import { useMemo, useState } from "react";
import type { Finding } from "@/lib/api";

const severityStyles: Record<string, string> = {
  CRITICAL: "bg-red-900/60 text-red-200",
  HIGH: "bg-orange-900/60 text-orange-200",
  MEDIUM: "bg-amber-900/60 text-amber-200",
  LOW: "bg-sky-900/60 text-sky-200",
  INFO: "bg-slate-800 text-slate-300",
};

export default function FindingsTable({ findings }: { findings: Finding[] }) {
  const [category, setCategory] = useState<string>("ALL");
  const [severity, setSeverity] = useState<string>("ALL");

  const categories = useMemo(
    () => Array.from(new Set(findings.map((f) => f.category))).sort(),
    [findings],
  );
  const severities = useMemo(
    () => Array.from(new Set(findings.map((f) => f.severity))).sort(),
    [findings],
  );

  const visible = findings.filter(
    (f) => (category === "ALL" || f.category === category) && (severity === "ALL" || f.severity === severity),
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3">
        <div>
          <label className="label">Categoría</label>
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="ALL">Todas</option>
            {categories.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Severidad</label>
          <select className="input" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="ALL">Todas</option>
            {severities.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500">
            <tr>
              <th className="px-2 py-2">Severidad</th>
              <th className="px-2 py-2">Categoría</th>
              <th className="px-2 py-2">Ubicación</th>
              <th className="px-2 py-2">Evidencia</th>
              <th className="px-2 py-2">Detalle</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((finding) => (
              <tr key={finding.id} className="border-t border-slate-800 align-top">
                <td className="px-2 py-2">
                  <span className={`rounded px-2 py-0.5 text-xs ${severityStyles[finding.severity] ?? "bg-slate-800"}`}>
                    {finding.severity}
                  </span>
                </td>
                <td className="px-2 py-2 font-mono text-xs">{finding.category}</td>
                <td className="px-2 py-2 font-mono text-xs text-slate-400">
                  {finding.file_path ?? "—"}
                  {finding.line_start ? `:${finding.line_start}` : ""}
                </td>
                <td className="px-2 py-2 text-xs">
                  <span
                    className={
                      finding.evidence_level === "DIRECT_EVIDENCE" ? "text-emerald-400" : "text-amber-400"
                    }
                  >
                    {finding.evidence_level}
                  </span>
                </td>
                <td className="px-2 py-2">
                  <p>{finding.message}</p>
                  {finding.snippet && (
                    <pre className="mt-1 overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-400">
                      {finding.snippet}
                    </pre>
                  )}
                </td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={5} className="px-2 py-4 text-center text-slate-500">
                  Sin hallazgos para los filtros seleccionados.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
