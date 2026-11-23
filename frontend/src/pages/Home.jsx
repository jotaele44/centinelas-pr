import React, { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, PlayCircle, ShieldCheck } from "lucide-react";
import { useLanguage } from "@/lib/LanguageContext";
import { useHomeEntryGate } from "@/lib/homeEntryGuard";

export default function Home() {
  const { t } = useLanguage();
  const homeAllowed = useHomeEntryGate("/dashboard");
  const [tourOpen, setTourOpen] = useState(true);
  if (!homeAllowed) return null;

  return (
    <main className="min-h-[calc(100vh-8rem)] bg-background text-foreground">
      <section className="border-b bg-gradient-to-b from-primary/10 to-background">
        <div className="max-w-5xl mx-auto px-4 py-14">
          <div className="flex items-center gap-3 mb-5">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <ShieldCheck className="h-8 w-8" />
            </div>
            <div>
              <span className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{t("CENTINELAS PR · INICIO")}</span>
              <h1 className="text-4xl font-bold">{t("Orientación antes del monitor")}</h1>
            </div>
          </div>
          <p className="max-w-3xl text-lg text-muted-foreground">
            {t("Esta página de inicio contiene la orientación y el Tour. El trabajo operativo comienza en Dashboard y las rutas especializadas permanecen separadas.")}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/dashboard" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">
              {t("Abrir Dashboard")} <ArrowRight className="h-4 w-4" />
            </Link>
            <button type="button" onClick={() => setTourOpen((value) => !value)} className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold">
              <PlayCircle className="h-4 w-4" /> {t("Tour")}
            </button>
          </div>
        </div>
      </section>
      {tourOpen ? (
        <section className="max-w-5xl mx-auto px-4 py-8">
          <h2 className="text-xl font-semibold mb-4">{t("Tour de Centinelas")}</h2>
          <ol className="space-y-3 text-muted-foreground list-decimal pl-5">
            <li>{t("Dashboard resume la postura operativa y el ciclo de trabajo.")}</li>
            <li>{t("Monitor, Señales y Asuntos separan observación, triage y continuidad de Matter.")}</li>
            <li>{t("Pipeline conserva clasificación, procedencia y estados sin promover coincidencias heurísticas a identidad.")}</li>
            <li>{t("Handoff entrega contexto a MoneySweep y TheHub mediante IDs y recibos verificables.")}</li>
          </ol>
        </section>
      ) : null}
    </main>
  );
}
