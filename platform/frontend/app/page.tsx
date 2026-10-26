"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, setOrgId, setToken, type Organization, type Session } from "@/lib/api";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Si ya hay una sesión activa, se continúa al panel; si no, se muestra el
    // formulario de acceso (no se salta la autenticación).
    if (getToken()) {
      router.replace("/dashboard");
    }
  }, [router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const path = mode === "register" ? "/api/v1/auth/register" : "/api/v1/auth/login";
      const body =
        mode === "register"
          ? { email, password, display_name: displayName, organization_name: organizationName }
          : { email, password };
      const session = await api<Session>(path, { method: "POST", body: JSON.stringify(body) });
      setToken(session.token);
      const organizations = await api<Organization[]>("/api/v1/organizations");
      if (organizations.length > 0) setOrgId(organizations[0].id);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error inesperado");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <h1 className="mb-1 text-xl font-semibold">Acceso</h1>
      <p className="mb-6 text-sm text-slate-400">
        Crea una organización y un proyecto para analizar código fuente.
      </p>

      <div className="card">
        <div className="mb-4 flex gap-2">
          <button
            type="button"
            className={mode === "register" ? "btn" : "btn-secondary"}
            onClick={() => setMode("register")}
          >
            Registro
          </button>
          <button
            type="button"
            className={mode === "login" ? "btn" : "btn-secondary"}
            onClick={() => setMode("login")}
          >
            Iniciar sesión
          </button>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label" htmlFor="auth-email">Correo</label>
            <input
              id="auth-email"
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="auth-password">Contraseña</label>
            <input
              id="auth-password"
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={10}
              required
            />
          </div>
          {mode === "register" && (
            <>
              <div>
                <label className="label" htmlFor="auth-name">Nombre</label>
                <input
                  id="auth-name"
                  className="input"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="label" htmlFor="auth-org">Organización</label>
                <input
                  id="auth-org"
                  className="input"
                  value={organizationName}
                  onChange={(e) => setOrganizationName(e.target.value)}
                  required
                />
              </div>
            </>
          )}
          {error && <p className="text-sm text-red-400">{error}</p>}
          <button className="btn w-full" disabled={busy}>
            {busy ? "Procesando…" : mode === "register" ? "Crear cuenta" : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
