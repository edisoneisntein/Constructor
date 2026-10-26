"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";
import ValidationPanel from "@/components/ValidationPanel";

export default function ValidatorPage() {
  const router = useRouter();

  useEffect(() => {
    // DEV MODE: skip auth check
    // if (!getToken()) router.replace("/");
  }, [router]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Validador de implementación</h1>
      <p className="text-sm text-slate-400">
        Comprueba, con evidencia reproducible sobre la versión actual del código, qué requisitos están
        realmente implementados. Una prueba omitida no cuenta como aprobada.
      </p>
      <ValidationPanel />
    </div>
  );
}
