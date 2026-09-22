import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Database, Newspaper, RadioTower, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import MatterTimeline from "@/components/lifecycle/MatterTimeline";
import ProgramTimeline from "@/components/ProgramTimeline";
import { useLanguage } from "@/lib/LanguageContext";

export default function Home() {
  const { t } = useLanguage();
  const programTimeline = [
    { id:"cent-signals", phase:"NOW", title:t("Señales públicas"), detail:t("Capturar, normalizar y preservar anuncios, agendas, RFP, vistas, comunicados, avisos y minutas con procedencia verificable."), category:t("Ingesta"), href:"/signals" },
    { id:"cent-triage", phase:"NEXT", title:t("Triage y clasificación"), detail:t("Clasificar dominio, confianza, evidencia y Matter ID sin promover coincidencias heurísticas a identidad."), category:t("Pipeline"), href:"/pipeline" },
    { id:"cent-matters", phase:"NEXT", title:t("Ciclo de Matter"), detail:t("Reconciliar señales relacionadas y mantener continuidad desde señal pública hasta oficialización."), category:t("Investigación"), href:"/matters" },
    { id:"cent-handoff", phase:"QUEUED", title:t("Handoff a MoneySweep y TheHub"), detail:t("Emitir contextos y recibos con IDs estables, hashes de manifestación y semántica de acknowledgement."), category:t("Federación"), href:"/handoff" },
    { id:"cent-cert", phase:"BLOCKED", title:t("Cierre de producción"), detail:t("La certificación final espera credenciales de transporte, frescura del productor, QA renderizado y receipts LOCKSTEP."), category:t("Certificación"), href:"/monitor" },
  ];
  return (
    <div>
      <section className="border-b bg-gradient-to-b from-primary/10 to-background">
        <div className="max-w-7xl mx-auto px-4 py-14">
          <div className="flex items-center gap-3 mb-5">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <ShieldCheck className="h-8 w-8" />
            </div>
            <div>
              <h1 className="text-4xl font-bold text-foreground">Centinelas</h1>
              <p className="text-muted-foreground">{t("Monitor temprano de información pública relevante a Puerto Rico")}</p>
            </div>
          </div>
          <p className="max-w-3xl text-lg text-foreground">
            {t("Captura lo que se anuncia, agenda, propone o notifica antes de que el proyecto, ley, contrato, permiso, pago o auditoría quede oficializado. MoneySweep cataloga el mismo asunto después de la oficialización.")}
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/monitor" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">
              {t("Abrir monitor")} <ArrowRight className="h-4 w-4" />
            </Link>
            <Link to="/handoff" className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold text-foreground">
              {t("Ver handoff MoneySweep")}
            </Link>
          </div>
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-4 py-8 space-y-8">
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-base"><RadioTower className="h-4 w-4" /> {t("Upstream")}</CardTitle></CardHeader>
            <CardContent className="text-sm text-muted-foreground">{t("Centinelas registra señales: anuncios, agendas, RFP, vistas, comunicados, avisos, minutas y declaraciones públicas.")}</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Database className="h-4 w-4" /> {t("Downstream")}</CardTitle></CardHeader>
            <CardContent className="text-sm text-muted-foreground">{t("MoneySweep registra el hecho oficial: contrato, ley, permiso, pago, auditoría, docket, enmienda o informe final.")}</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Newspaper className="h-4 w-4" /> {t("Reporting")}</CardTitle></CardHeader>
            <CardContent className="text-sm text-muted-foreground">{t("El Matter ID une señales, evidencia, leads editoriales y registros oficiales en una línea de vida verificable.")}</CardContent>
          </Card>
        </div>
        <ProgramTimeline items={programTimeline} />
        <MatterTimeline currentStage="pending_officialization" />
      </section>
    </div>
  );
}
