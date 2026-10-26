"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  clearSession,
  deleteProject,
  getOrgId,
  getToken,
  setOrgId,
  type Organization,
  type Project,
} from "@/lib/api";
import UsagePanel from "@/components/UsagePanel";

export default function DashboardPage() {
  const router = useRouter();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(
    async (orgId?: string) => {
      const organizationsList = await api<Organization[]>("/api/v1/organizations");
      setOrganizations(organizationsList);
      const active = orgId ?? getOrgId() ?? organizationsList[0]?.id;
      if (active) {
        setOrgId(active);
        setProjects(await api<Project[]>("/api/v1/projects"));
      }
    },
    [],
  );

  useEffect(() => {
    if (!getToken()) {
      router.replace("/");
      return;
    }
    load()
      .catch((err) => setError(err instanceof Error ? err.message : "Error"))
      .finally(() => setLoading(false));
  }, [load, router]);

  async function createProject(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api<Project>("/api/v1/projects", { method: "POST", body: JSON.stringify({ name }) });
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    }
  }

  async function switchOrganization(id: string) {
    setOrgId(id);
    await load(id);
  }

  async function removeProject(project: Project) {
    if (
      !window.confirm(
        `¿Eliminar el proyecto "${project.name}" y todos sus análisis? Esta acción no se puede deshacer.`,
      )
    ) {
      return;
    }
    setError(null);
    setDeleting(project.id);
    try {
      await deleteProject(project.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al eliminar el proyecto");
    } finally {
      setDeleting(null);
    }
  }

  if (loading) return <p className="text-sm text-slate-400">Cargando…</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Proyectos</h1>
          <p className="text-sm text-slate-400">{projects.length} proyecto(s) en la organización activa.</p>
        </div>
        <button
          className="btn-secondary"
          onClick={() => {
            clearSession();
            router.replace("/");
          }}
        >
          Salir
        </button>
      </div>

      {organizations.length > 1 && (
        <div className="card">
          <label className="label">Organización activa</label>
          <select
            className="input"
            value={getOrgId() ?? ""}
            onChange={(e) => switchOrganization(e.target.value)}
          >
            {organizations.map((organization) => (
              <option key={organization.id} value={organization.id}>
                {organization.name} ({organization.role})
              </option>
            ))}
          </select>
        </div>
      )}

      <UsagePanel refreshKey={projects.length + ":" + (getOrgId() ?? "")} />

      <form onSubmit={createProject} className="card flex items-end gap-3">
        <div className="flex-1">
          <label className="label">Nuevo proyecto</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nombre" required />
        </div>
        <button className="btn">Crear</button>
      </form>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="grid gap-3 sm:grid-cols-2">
        {projects.map((project) => (
          <div key={project.id} className="card flex items-start justify-between gap-3">
            <button
              className="flex-1 text-left transition hover:text-sky-400"
              onClick={() => router.push(`/projects/${project.id}`)}
            >
              <p className="font-medium">{project.name}</p>
              <p className="mt-1 text-xs text-slate-500">Creado {project.created_at}</p>
            </button>
            <button
              className="btn-danger px-2 py-1 text-xs"
              onClick={() => removeProject(project)}
              disabled={deleting === project.id}
              title="Eliminar proyecto"
            >
              {deleting === project.id ? "Eliminando…" : "Eliminar"}
            </button>
          </div>
        ))}
        {projects.length === 0 && <p className="text-sm text-slate-500">Aún no hay proyectos.</p>}
      </div>
    </div>
  );
}
