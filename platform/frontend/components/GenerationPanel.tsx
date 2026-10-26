"use client";

import { useState } from "react";
import { createGeneration, type Generation } from "@/lib/api";

export default function GenerationPanel({ analysisId }: { analysisId: string }) {
  const [instruction, setInstruction] = useState("");
  const [targetPath, setTargetPath] = useState("");
  const [mode, setMode] = useState<"feature" | "repair">("feature");
  const [consent, setConsent] = useState(false);
  const [result, setResult] = useState<Generation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!consent) {
      setError("Confirme el consentimiento de transmisión a NVIDIA NIM (§14).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const generation = await createGeneration(analysisId, {
        instruction,
        target_path: targetPath.trim() || null,
        mode,
        ai_consent: true,
      });
      setResult(generation);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-slate-300">Generación con IA · NVIDIA NIM (§10)</h3>
      {error && <p className="text-sm text-red-400">{error}</p>}

      <form onSubmit={submit} className="space-y-3 rounded border border-slate-800 p-3">
        <div>
          <label className="label" htmlFor="gen-instruction">
            Instrucción
          </label>
          <textarea
            id="gen-instruction"
            className="input h-20"
            placeholder="Describe el cambio o la corrección a realizar"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            required
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className="label" htmlFor="gen-target">
              Archivo objetivo
            </label>
            <input
              id="gen-target"
              className="input font-mono text-xs"
              placeholder="src/app.py"
              value={targetPath}
              onChange={(e) => setTargetPath(e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="gen-mode">
              Modo
            </label>
            <select
              id="gen-mode"
              className="input"
              value={mode}
              onChange={(e) => setMode(e.target.value as "feature" | "repair")}
            >
              <option value="feature">feature (nuevo cambio)</option>
              <option value="repair">repair (reparar hallazgos)</option>
            </select>
          </div>
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-400">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          Autorizo enviar fragmentos de código a NVIDIA NIM para generar el cambio.
        </label>
        <button className="btn" disabled={busy}>
          {busy ? "Generando…" : "Generar con NIM"}
        </button>
      </form>

      {result && <GenerationResultView generation={result} />}
    </div>
  );
}

function GenerationResultView({ generation }: { generation: Generation }) {
  const verification = generation.verification;
  return (
    <div className="space-y-3 rounded border border-slate-800 p-3">
      <div className="text-xs text-slate-400">
        <p>{generation.summary}</p>
        <p className="mt-1">
          Modelo {generation.model} · modo {generation.mode} · {generation.latency_ms} ms · cambio{" "}
          <span className="font-mono">{generation.change_set.id}</span> ({generation.change_set.status})
        </p>
      </div>

      {generation.limitations.length > 0 && (
        <ul className="list-disc pl-5 text-xs text-amber-300">
          {generation.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}

      <table className="w-full text-left text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="py-1">Archivo</th>
            <th className="py-1">Lenguaje</th>
            <th className="py-1">Tipo</th>
            <th className="py-1">Sintaxis</th>
            <th className="py-1">+/−</th>
          </tr>
        </thead>
        <tbody>
          {verification.map((item) => (
            <tr key={item.path} className="border-t border-slate-800">
              <td className="py-1 font-mono">{item.path}</td>
              <td className="py-1">{item.language}</td>
              <td className="py-1">{item.change_type}</td>
              <td className="py-1">
                {!item.syntax_checked ? (
                  <span className="text-amber-300">no verificada</span>
                ) : item.syntax_ok ? (
                  <span className="text-emerald-400">OK</span>
                ) : (
                  <span className="text-red-400">error</span>
                )}
              </td>
              <td className="py-1">
                +{item.additions}/−{item.deletions}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {generation.change_set.files.map((file) => (
        <div key={file.id} className="rounded border border-slate-800">
          <div className="border-b border-slate-800 px-3 py-1 font-mono text-xs">{file.path}</div>
          {file.unified_diff ? (
            <pre className="overflow-x-auto p-2 text-xs">
              {file.unified_diff.split("\n").map((line, index) => {
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
          ) : (
            <p className="px-3 py-2 text-xs text-slate-500">Sin diff.</p>
          )}
        </div>
      ))}

      <p className="text-xs text-slate-500">
        Revise y apruebe el cambio en el panel «Cambios propuestos».
      </p>
    </div>
  );
}
