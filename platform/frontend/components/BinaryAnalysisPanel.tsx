"use client";

import { useCallback, useEffect, useState } from "react";
import {
  analyzeBinary,
  listBinaryAnalyses,
  uploadBinary,
  type BinaryAnalysis,
} from "@/lib/api";

export default function BinaryAnalysisPanel({ projectId }: { projectId: string }) {
  const [analyses, setAnalyses] = useState<BinaryAnalysis[]>([]);
  const [detail, setDetail] = useState<BinaryAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const list = await listBinaryAnalyses(projectId);
    setAnalyses(list);
    return list;
  }, [projectId]);

  useEffect(() => {
    setDetail(null);
    setAnalyses([]);
    refresh().catch((err) => setError(err instanceof Error ? err.message : "Error"));
  }, [refresh]);

  async function onUpload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const artifact = await uploadBinary(projectId, file);
      const analysis = await analyzeBinary(projectId, artifact.id);
      setDetail(analysis);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">Análisis de binarios (§6.2)</h3>
        <label className="btn cursor-pointer">
          {busy ? "Analizando…" : "Subir binario"}
          <input
            type="file"
            className="hidden"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUpload(file);
              event.target.value = "";
            }}
          />
        </label>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <ul className="space-y-2">
        {analyses.map((analysis) => (
          <li
            key={analysis.id}
            className={`cursor-pointer rounded border px-3 py-2 text-sm ${
              detail?.id === analysis.id ? "border-sky-600 bg-slate-800/60" : "border-slate-800"
            }`}
            onClick={() => setDetail(analysis)}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs">{analysis.format}</span>
              <span className="text-xs text-slate-400">
                {analysis.architecture ?? "?"} · {analysis.bits ?? "?"} bits · {analysis.file_type ?? "?"}
              </span>
            </div>
          </li>
        ))}
        {analyses.length === 0 && <li className="text-sm text-slate-500">Sin binarios analizados.</li>}
      </ul>

      {detail && <BinaryDetail analysis={detail} />}
    </div>
  );
}

function BinaryDetail({ analysis }: { analysis: BinaryAnalysis }) {
  const facts = analysis.facts;
  return (
    <div className="space-y-4 rounded border border-slate-800 p-3 text-xs">
      <div className="text-slate-400">
        <p>
          {facts.format} · {facts.architecture ?? "?"} · {facts.bits ?? "?"} bits ·{" "}
          {facts.file_type ?? "?"} · {facts.size_bytes} bytes
        </p>
        <p className="break-all font-mono">sha256: {facts.sha256}</p>
      </div>

      <FactList title={`Secciones (${facts.sections.length})`}>
        {facts.sections.map((section, index) => (
          <li key={index} className="font-mono">
            {section.name} · {section.size} B
            {section.entropy !== null ? ` · H=${section.entropy}` : ""}
          </li>
        ))}
      </FactList>

      <FactList title={`Símbolos importados (${facts.imported_symbols.length})`}>
        {facts.imported_symbols.map((symbol, index) => (
          <li key={index} className="font-mono">
            {symbol}
          </li>
        ))}
      </FactList>

      <FactList title={`Símbolos exportados (${facts.exported_symbols.length})`}>
        {facts.exported_symbols.map((symbol, index) => (
          <li key={index} className="font-mono">
            {symbol}
          </li>
        ))}
      </FactList>

      <FactList title={`Librerías (${facts.linked_libraries.length})`}>
        {facts.linked_libraries.map((library, index) => (
          <li key={index} className="font-mono">
            {library}
          </li>
        ))}
      </FactList>

      {facts.runtime_indicators.length > 0 && (
        <FactList title="Indicadores de runtime">
          {facts.runtime_indicators.map((indicator, index) => (
            <li key={index}>{indicator}</li>
          ))}
        </FactList>
      )}

      {facts.strings_sample.length > 0 && (
        <FactList title="Cadenas relevantes">
          {facts.strings_sample.map((value, index) => (
            <li key={index} className="break-all font-mono text-slate-400">
              {value}
            </li>
          ))}
        </FactList>
      )}

      {facts.embedded && facts.embedded.length > 0 && (
        <FactList title={`Contenido interno inspeccionado (${facts.embedded.length})`}>
          {facts.embedded.map((entry, index) => (
            <li key={index} className="font-mono">
              [{entry.format}] {entry.name}
              {entry.version ? ` · v${entry.version}` : ""}
            </li>
          ))}
        </FactList>
      )}

      {facts.limitations.length > 0 && (
        <div>
          <p className="mb-1 uppercase text-amber-300/80">Limitaciones</p>
          <ul className="list-disc space-y-1 pl-5 text-amber-300/80">
            {facts.limitations.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-slate-500">
        Las cadenas, símbolos y firmas son evidencia contextual, no prueba de funcionalidad (§6.2).
      </p>
    </div>
  );
}

function FactList({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 uppercase text-slate-500">{title}</p>
      <ul className="max-h-48 space-y-0.5 overflow-y-auto text-slate-400">{children}</ul>
    </div>
  );
}
