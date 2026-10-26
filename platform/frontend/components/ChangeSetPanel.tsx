"use client";

import { useCallback, useEffect, useState } from "react";
import {
  applyChangeSet,
  approveChangeSet,
  createChangeSet,
  getChangeSet,
  listChangeSets,
  rollbackChangeSet,
  validateChangeSet,
  type ChangeFile,
  type ChangeSet,
  type ChangeSetDetail,
  type FileEditInput,
} from "@/lib/api";

type DraftEdit = { path: string; content: string; remove: boolean };

const statusStyles: Record<string, string> = {
  PROPOSED: "bg-amber-900/60 text-amber-200",
  APPROVED: "bg-sky-900/60 text-sky-200",
  APPLIED: "bg-indigo-900/60 text-indigo-200",
  VALIDATED: "bg-emerald-900/60 text-emerald-200",
  ROLLED_BACK: "bg-slate-800 text-slate-300",
  REJECTED: "bg-red-900/60 text-red-200",
};

export default function ChangeSetPanel({ analysisId }: { analysisId: string }) {
  const [changeSets, setChangeSets] = useState<ChangeSet[]>([]);
  const [detail, setDetail] = useState<ChangeSetDetail | null>(null);
  const [reason, setReason] = useState("");
  const [rule, setRule] = useState("R-14");
  const [edits, setEdits] = useState<DraftEdit[]>([{ path: "", content: "", remove: false }]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const list = await listChangeSets(analysisId);
    setChangeSets(list);
    return list;
  }, [analysisId]);

  useEffect(() => {
    setDetail(null);
    setChangeSets([]);
    refresh().catch((err) => setError(err instanceof Error ? err.message : "Error"));
  }, [refresh]);

  async function run(action: () => Promise<ChangeSetDetail | void>) {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      if (result) setDetail(result);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const payloadEdits: FileEditInput[] = edits
      .filter((edit) => edit.path.trim())
      .map((edit) => ({ path: edit.path.trim(), new_content: edit.remove ? null : edit.content }));
    if (payloadEdits.length === 0) {
      setError("Añade al menos un archivo al conjunto de cambios.");
      return;
    }
    await run(() => createChangeSet(analysisId, { reason, produced_by_rule: rule, edits: payloadEdits }));
    setReason("");
    setEdits([{ path: "", content: "", remove: false }]);
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-slate-300">Cambios propuestos (§15)</h3>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="grid gap-4 lg:grid-cols-2">
        <form onSubmit={submit} className="space-y-3 rounded border border-slate-800 p-3">
          <h4 className="text-xs uppercase text-slate-500">Nuevo conjunto de cambios</h4>
          <div>
            <label className="label">Motivo</label>
            <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} required />
          </div>
          <div>
            <label className="label">Regla / tarea que lo produce</label>
            <input className="input" value={rule} onChange={(e) => setRule(e.target.value)} required />
          </div>
          <div className="space-y-2">
            <label className="label">Ediciones</label>
            {edits.map((edit, index) => (
              <div key={index} className="space-y-1 rounded border border-slate-800 p-2">
                <input
                  className="input font-mono text-xs"
                  placeholder="src/app.py"
                  value={edit.path}
                  onChange={(e) =>
                    setEdits((prev) => prev.map((item, i) => (i === index ? { ...item, path: e.target.value } : item)))
                  }
                />
                <textarea
                  className="input h-24 font-mono text-xs"
                  placeholder="Nuevo contenido del archivo"
                  value={edit.content}
                  disabled={edit.remove}
                  onChange={(e) =>
                    setEdits((prev) =>
                      prev.map((item, i) => (i === index ? { ...item, content: e.target.value } : item)),
                    )
                  }
                />
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <label className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={edit.remove}
                      onChange={(e) =>
                        setEdits((prev) =>
                          prev.map((item, i) => (i === index ? { ...item, remove: e.target.checked } : item)),
                        )
                      }
                    />
                    Eliminar archivo
                  </label>
                  <button
                    type="button"
                    className="text-red-400"
                    onClick={() => setEdits((prev) => prev.filter((_, i) => i !== index))}
                  >
                    Quitar
                  </button>
                </div>
              </div>
            ))}
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setEdits((prev) => [...prev, { path: "", content: "", remove: false }])}
            >
              Añadir archivo
            </button>
          </div>
          <button className="btn" disabled={busy}>
            Crear conjunto
          </button>
        </form>

        <div className="space-y-3 rounded border border-slate-800 p-3">
          <h4 className="text-xs uppercase text-slate-500">Conjuntos del análisis ({changeSets.length})</h4>
          <ul className="space-y-2">
            {changeSets.map((item) => (
              <li
                key={item.id}
                className={`cursor-pointer rounded border px-3 py-2 text-sm ${
                  detail?.id === item.id ? "border-sky-600 bg-slate-800/60" : "border-slate-800"
                }`}
                onClick={() =>
                  run(() => getChangeSet(item.id)).then(() => undefined)
                }
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs">{item.id}</span>
                  <span className={`rounded px-2 py-0.5 text-xs ${statusStyles[item.status] ?? "bg-slate-800"}`}>
                    {item.status}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {item.reason} · regla {item.produced_by_rule}
                </p>
              </li>
            ))}
            {changeSets.length === 0 && <li className="text-sm text-slate-500">Sin conjuntos todavía.</li>}
          </ul>
        </div>
      </div>

      {detail && <ChangeSetDetailView detail={detail} busy={busy} run={run} />}
    </div>
  );
}

function ChangeSetDetailView({
  detail,
  busy,
  run,
}: {
  detail: ChangeSetDetail;
  busy: boolean;
  run: (action: () => Promise<ChangeSetDetail | void>) => Promise<void>;
}) {
  return (
    <div className="space-y-3 rounded border border-slate-800 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-mono text-xs text-slate-400">{detail.id}</p>
          <p className="text-sm">{detail.reason}</p>
          <p className="text-xs text-slate-500">
            Regla: {detail.produced_by_rule} · reversible: {detail.reversible ? "sí" : "no"} · artefacto{" "}
            {detail.base_artifact_sha256?.slice(0, 12) ?? "—"}…
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {detail.status === "PROPOSED" && (
            <>
              <button
                className="btn"
                disabled={busy}
                onClick={() => run(() => approveChangeSet(detail.id, "approved"))}
              >
                Aprobar
              </button>
              <button
                className="btn-secondary"
                disabled={busy}
                onClick={() => run(() => approveChangeSet(detail.id, "rejected"))}
              >
                Rechazar
              </button>
            </>
          )}
          {detail.status === "APPROVED" && (
            <button className="btn" disabled={busy} onClick={() => run(() => applyChangeSet(detail.id))}>
              Aplicar
            </button>
          )}
          {detail.status === "APPLIED" && (
            <button className="btn" disabled={busy} onClick={() => run(() => validateChangeSet(detail.id))}>
              Validar
            </button>
          )}
          {(detail.status === "APPLIED" || detail.status === "VALIDATED") && (
            <button
              className="btn-secondary"
              disabled={busy}
              onClick={() => run(() => rollbackChangeSet(detail.id))}
            >
              Revertir
            </button>
          )}
        </div>
      </div>

      {detail.external_effects && <p className="text-xs text-slate-500">{detail.external_effects}</p>}

      {detail.validation_result && (
        <pre className="overflow-x-auto rounded bg-slate-950 p-2 text-xs text-slate-300">
          {JSON.stringify(detail.validation_result, null, 2)}
        </pre>
      )}

      <div className="space-y-2">
        {detail.files.map((file) => (
          <FileChangeView key={file.id} file={file} />
        ))}
      </div>

      {detail.approvals.length > 0 && (
        <div>
          <p className="mb-1 text-xs uppercase text-slate-500">Aprobaciones</p>
          <ul className="space-y-1 text-xs text-slate-400">
            {detail.approvals.map((approval) => (
              <li key={approval.id}>
                {approval.decision} por {approval.user_id} · {approval.created_at}
                {approval.comment ? ` — ${approval.comment}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function FileChangeView({ file }: { file: ChangeFile }) {
  return (
    <div className="rounded border border-slate-800">
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-1 text-xs">
        <span className="font-mono">{file.path}</span>
        <span className="text-slate-400">{file.change_type}</span>
      </div>
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
  );
}
