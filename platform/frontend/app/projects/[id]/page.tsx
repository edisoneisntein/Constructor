"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import ChangeSetPanel from "@/components/ChangeSetPanel";
import GenerationPanel from "@/components/GenerationPanel";
import FindingsTable from "@/components/FindingsTable";
import GraphView from "@/components/GraphView";
import MigrationPanel from "@/components/MigrationPanel";
import BinaryAnalysisPanel from "@/components/BinaryAnalysisPanel";
import {
  api,
  deleteProject,
  downloadExport,
  getToken,
  type AnalysisSummary,
  type ArchitectureGraph,
  type Artifact,
  type Finding,
  type GraphEdge,
  type Job,
  type NodeDetail,
  type Project,
} from "@/lib/api";

const ACTIVE_STATUSES = new Set(["QUEUED", "ANALYZING", "GRAPH_BUILDING"]);

export default function ProjectPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = params.id;

  const [project, setProject] = useState<Project | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [analyses, setAnalyses] = useState<Job[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [summary, setSummary] = useState<AnalysisSummary | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [graph, setGraph] = useState<ArchitectureGraph | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [nodeDetail, setNodeDetail] = useState<NodeDetail | null>(null);
  const [deepAnalysis, setDeepAnalysis] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const loadDetail = useCallback(
    async (analysisId: string) => {
      const [analysisSummary, findingPage, architecture] = await Promise.all([
        api<AnalysisSummary>(`/api/v1/analyses/${analysisId}`),
        api<{ items: Finding[]; total: number }>(`/api/v1/analyses/${analysisId}/findings?limit=500`),
        api<ArchitectureGraph>(`/api/v1/analyses/${analysisId}/architecture`),
      ]);
      setSummary(analysisSummary);
      setFindings(findingPage.items);
      setGraph(architecture);
      return analysisSummary;
    },
    [],
  );

  const loadBase = useCallback(async () => {
    const [projectData, artifactList, jobList] = await Promise.all([
      api<Project>(`/api/v1/projects/${projectId}`),
      api<Artifact[]>(`/api/v1/projects/${projectId}/artifacts`),
      api<Job[]>(`/api/v1/projects/${projectId}/analyses`),
    ]);
    setProject(projectData);
    setArtifacts(artifactList);
    setAnalyses(jobList);
    return jobList;
  }, [projectId]);

  useEffect(() => {
    if (!getToken()) return;
    loadBase()
      .then((jobs) => {
        if (jobs.length > 0) setSelected(jobs[0].id);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Error"));
  }, [loadBase]);

  useEffect(() => {
    setSelectedNodeId(null);
    setNodeDetail(null);
    if (!selected) return;
    loadDetail(selected).catch((err) => setError(err instanceof Error ? err.message : "Error"));
  }, [selected, loadDetail]);

  async function selectNode(nodeId: string) {
    setSelectedNodeId(nodeId);
    try {
      const detail = await api<NodeDetail>(
        `/api/v1/analyses/${selected}/architecture/node?node_id=${encodeURIComponent(nodeId)}`,
      );
      setNodeDetail(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al inspeccionar el nodo");
    }
  }

  useEffect(() => {
    const hasActive = analyses.some((job) => ACTIVE_STATUSES.has(job.status));
    if (!hasActive) return;
    const timer = setInterval(async () => {
      const jobs = await loadBase();
      if (selected) await loadDetail(selected);
      if (!jobs.some((job) => ACTIVE_STATUSES.has(job.status))) clearInterval(timer);
    }, 1500);
    return () => clearInterval(timer);
  }, [analyses, loadBase, loadDetail, selected]);

  async function upload(event: React.FormEvent) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      await api<Artifact>(`/api/v1/projects/${projectId}/artifacts`, { method: "POST", body: form });
      if (fileInput.current) fileInput.current.value = "";
      await loadBase();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al subir");
    } finally {
      setBusy(false);
    }
  }

  async function startAnalysis() {
    if (artifacts.length === 0) {
      setError("Sube primero un artefacto ZIP.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const job = await api<Job>(`/api/v1/projects/${projectId}/analyses`, {
        method: "POST",
        body: JSON.stringify({ artifact_id: artifacts[0].id, deep_analysis: deepAnalysis }),
      });
      setSelected(job.id);
      await loadBase();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al iniciar el análisis");
    } finally {
      setBusy(false);
    }
  }

  async function cancelAnalysis() {
    if (!selected) return;
    try {
      await api<Job>(`/api/v1/analyses/${selected}/cancel`, { method: "POST" });
      await loadBase();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cancelar");
    }
  }

  async function removeProject() {
    if (
      !window.confirm(
        `¿Eliminar el proyecto "${project?.name ?? projectId}" y todos sus análisis? Esta acción no se puede deshacer.`,
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await deleteProject(projectId);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al eliminar el proyecto");
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{project?.name ?? "Proyecto"}</h1>
          <p className="text-sm text-slate-400">{project?.id}</p>
        </div>
        <button className="btn-danger" onClick={removeProject} disabled={deleting}>
          {deleting ? "Eliminando…" : "Eliminar proyecto"}
        </button>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <section className="card space-y-3">
        <h2 className="font-medium">1. Artefacto de origen</h2>
        <form onSubmit={upload} className="flex flex-wrap items-center gap-3">
          <input
            ref={fileInput}
            type="file"
            accept=".zip,application/zip"
            className="text-sm text-slate-300"
          />
          <button className="btn" disabled={busy}>
            Subir ZIP
          </button>
        </form>
        {artifacts.length > 0 && (
          <ul className="space-y-1 text-sm text-slate-300">
            {artifacts.map((artifact) => (
              <li key={artifact.id} className="font-mono text-xs">
                {artifact.filename} · {artifact.detected_mime} · sha256 {artifact.sha256.slice(0, 12)}…
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card space-y-3">
        <h2 className="font-medium">2. Ejecutar análisis estático</h2>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={deepAnalysis} onChange={(e) => setDeepAnalysis(e.target.checked)} />
          Análisis profundo (adaptador REA, JS/TS)
        </label>
        <button className="btn" onClick={startAnalysis} disabled={busy}>
          Iniciar análisis
        </button>

        <ul className="space-y-2">
          {analyses.map((job) => (
            <li
              key={job.id}
              className={`flex cursor-pointer items-center justify-between rounded border px-3 py-2 text-sm ${
                selected === job.id ? "border-sky-600 bg-slate-800/60" : "border-slate-800"
              }`}
              onClick={() => setSelected(job.id)}
            >
              <span className="font-mono text-xs">{job.id}</span>
              <span className="flex items-center gap-3 text-xs">
                <span>{job.status}</span>
                <span className="text-slate-500">
                  {job.progress_completed}/{job.progress_total}
                </span>
              </span>
            </li>
          ))}
          {analyses.length === 0 && <p className="text-sm text-slate-500">Sin análisis todavía.</p>}
        </ul>

        {selected && summary && ACTIVE_STATUSES.has(summary.job.status) && (
          <button className="btn-secondary" onClick={cancelAnalysis}>
            Cancelar análisis
          </button>
        )}
      </section>

      {summary && (
        <section className="card space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-medium">3. Resultados</h2>
            <div className="flex gap-2">
              <button className="btn-secondary" onClick={() => downloadExport(summary.job.id, "json")}>
                Exportar JSON
              </button>
              <button className="btn-secondary" onClick={() => downloadExport(summary.job.id, "markdown")}>
                Exportar Markdown
              </button>
            </div>
          </div>

          {summary.job.status === "FAILED" && (
            <p className="text-sm text-red-400">
              Falló: {summary.job.error_code} — {summary.job.error_message}
            </p>
          )}

          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <Metric label="Estado" value={summary.job.status} />
            <Metric label="Hallazgos" value={String(summary.finding_count)} />
            <Metric label="Nodos" value={String(summary.node_count)} />
            <Metric label="Aristas" value={String(summary.edge_count)} />
            <Metric label="Dependencias" value={String(summary.dependency_count)} />
            <Metric label="Archivos analizados" value={String(summary.files_analyzed)} />
            <Metric label="Lenguajes" value={summary.languages.join(", ") || "—"} />
            <Metric label="Progreso" value={summary.progress_formula} />
          </div>

          <div>
            <h3 className="mb-2 text-sm font-medium text-slate-300">Hallazgos</h3>
            <FindingsTable findings={findings} />
          </div>

          <div>
            <h3 className="mb-2 text-sm font-medium text-slate-300">Grafo de arquitectura</h3>
            {graph && graph.nodes.length > 0 ? (
              <GraphView graph={graph} selectedNodeId={selectedNodeId} onSelectNode={selectNode} />
            ) : (
              <p className="text-sm text-slate-500">El grafo aún no tiene nodos.</p>
            )}
            {nodeDetail && <NodeInspector detail={nodeDetail} />}
          </div>

          <div>
            <ChangeSetPanel analysisId={summary.job.id} />
          </div>

          <div>
            <GenerationPanel analysisId={summary.job.id} />
          </div>

          <div>
            <MigrationPanel projectId={projectId} analysisId={summary.job.id} />
          </div>

          <div>
            <BinaryAnalysisPanel projectId={projectId} />
          </div>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-800 p-2">
      <p className="text-xs uppercase text-slate-500">{label}</p>
      <p className="truncate text-sm">{value}</p>
    </div>
  );
}

function NodeInspector({ detail }: { detail: NodeDetail }) {
  return (
    <div className="mt-3 rounded border border-slate-800 p-3 text-sm">
      <p className="font-medium">{detail.node.label}</p>
      <p className="text-xs text-slate-500">
        {detail.node.node_type} · {detail.node.evidence_level}
        {detail.node.path ? ` · ${detail.node.path}` : ""}
      </p>
      <div className="mt-2 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-xs uppercase text-slate-500">Salientes ({detail.outgoing_edges.length})</p>
          <ul className="space-y-1 text-xs">
            {detail.outgoing_edges.map((edge: GraphEdge) => (
              <li key={edge.id} className="font-mono">
                {edge.edge_type} → {edge.target_node_id ?? edge.target_ref ?? "—"} ({edge.evidence_level})
              </li>
            ))}
            {detail.outgoing_edges.length === 0 && <li className="text-slate-600">—</li>}
          </ul>
        </div>
        <div>
          <p className="mb-1 text-xs uppercase text-slate-500">Entrantes ({detail.incoming_edges.length})</p>
          <ul className="space-y-1 text-xs">
            {detail.incoming_edges.map((edge: GraphEdge) => (
              <li key={edge.id} className="font-mono">
                {edge.source_node_id} → {edge.edge_type} ({edge.evidence_level})
              </li>
            ))}
            {detail.incoming_edges.length === 0 && <li className="text-slate-600">—</li>}
          </ul>
        </div>
      </div>
    </div>
  );
}
