import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Database, Newspaper, RadioTower, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import MatterTimeline from "@/components/lifecycle/MatterTimeline";

export default function Home() {
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
              <p className="text-muted-foreground">Monitor temprano de información pública relevante a Puerto Rico</p>
            </div>
          </div>
          <p className="max-w-3xl text-lg text-foreground">
            Captura lo que se anuncia, agenda, propone o notifica antes de que el proyecto, ley, contrato, permiso, pago o auditoría quede oficializado. MoneySweep cataloga el mismo asunto después de la oficialización.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/monitor" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">
              Abrir monitor <ArrowRight className="h-4 w-4" />
            </Link>
            <Link to="/handoff" className="inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm font-semibold text-foreground">
              Ver handoff MoneySweep
            </Link>
          </div>
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-4 py-8 space-y-8">
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-base"><RadioTower className="h-4 w-4" /> Upstream</CardTitle></CardHeader>
            <CardContent className="text-sm text-muted-foreground">Centinelas registra señales: anuncios, agendas, RFP, vistas, comunicados, avisos, minutas y declaraciones públicas.</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Database className="h-4 w-4" /> Downstream</CardTitle></CardHeader>
            <CardContent className="text-sm text-muted-foreground">MoneySweep registra el hecho oficial: contrato, ley, permiso, pago, auditoría, docket, enmienda o informe final.</CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Newspaper className="h-4 w-4" /> Reporting</CardTitle></CardHeader>
            <CardContent className="text-sm text-muted-foreground">El Matter ID une señales, evidencia, leads editoriales y registros oficiales en una línea de vida verificable.</CardContent>
          </Card>
        </div>
        <MatterTimeline currentStage="pending_officialization" />
      </section>
    </div>
  );
}
