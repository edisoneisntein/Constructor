import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Plataforma de Análisis y Migración",
  description: "Análisis estático de código, hallazgos y grafo de arquitectura.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <header className="border-b border-slate-800">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
            <a href="/dashboard" className="text-sm font-semibold text-sky-400">
              Plataforma de Análisis y Migración
            </a>
            <nav className="flex items-center gap-4 text-xs">
              <a href="/dashboard" className="text-slate-400 hover:text-sky-400">
                Proyectos
              </a>
              <a href="/validator" className="text-slate-400 hover:text-sky-400">
                Validador
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
