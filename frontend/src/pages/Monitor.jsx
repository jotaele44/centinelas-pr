import React, { useEffect, useMemo, useState } from "react";
import { appClient } from "@/api/appClient";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, Database, Newspaper, RadioTower } from "lucide-react";
import MetricCard from "@/components/monitor/MetricCard";
import SignalCard from "@/components/monitor/SignalCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { mapLegacyLawToMatter, mapLegacyLawToSignal } from "@/lib/lifecycle";

async function safeList(entityName, sort = "-captured_at", limit = 100) {
  const entity = appClient.entities?.[entityName];
  if (!entity?.list) return [];
  try {
    return await entity.list(sort, limit);
  } catch (_error) {
    return [];
  }
}

export default function Monitor() {
  const [signals, setSignals] = useState([]);
  const [matters, setMatters] = useState([]);
  const [sources, setSources] = useState([]);
  const [handoffs, setHandoffs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function loadMonitor() {
      const [signalRows, matterRows, sourceRows, handoffRows, legacyLaws] = await Promise.all([
        safeList("Signal", "-captured_at", 100),
        safeList("Matter", "-first_seen_at", 100),
        safeList("Source", "name", 200),
        safeList("HandoffCandidate", "-created_date", 50),
        safeList("Law", "-last_action_date", 50),
      ]);

      if (!active) return;
      const derivedSignals = signalRows.length > 0 ? signalRows : legacyLaws.map(mapLegacyLawToSignal);
      const derivedMatters = matterRows.length > 0 ? matterRows : legacyLaws.map(mapLegacyLawToMatter);
      setSignals(derivedSignals);
      setMatters(derivedMatters);
      setSources(sourceRows);
      setHandoffs(handoffRows);
      setLoading(false);
    }
    loadMonitor();
    return () => {
      active = false;
    };
  }, []);

  const stats = useMemo(() => {
    const ready = signals.filter((signal) => signal.handoff_status === "ready_for_moneysweep").length + handoffs.length;
    const highConfidence = signals.filter((signal) => Number(signal.confidence_score || 0) >= 85).length;
    const staleSources = sources.filter((source) => ["broken", "stale", "manual"].includes(source.status)).length;
    return { ready, highConfidence, staleSources };
  }, [handoffs.length, signals, sources]);

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
      <section className="rounded-2xl border bg-gradient-to-b from-primary/5 to-background p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-primary">Centinelas</p>
            <h1 className="mt-1 text-3xl font-bold text-foreground">Monitor temprano de información pública de Puerto Rico</h1>
            <p className="mt-3 max-w-3xl text-muted-foreground">
              Captura señales antes de que se conviertan en ley, contrato, permiso, pago, auditoría o expediente oficial. MoneySweep cataloga el registro oficial posterior.
            </p>
          </div>
          <Link to="/handoff" className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">
            Ver handoff <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-4">
        <MetricCard label="Señales capturadas" value={loading ? "…" : signals.length} detail="Upstream: anuncios, agendas, RFP, vistas, avisos." />
        <MetricCard label="Asuntos públicos" value={loading ? "…" : matters.length} detail="Objetos compartidos con MoneySweep." />
        <MetricCard label="Listos para MoneySweep" value={loading ? "…" : stats.ready} detail="Oficialización detectada o candidata." />
        <MetricCard label="Fuentes con brecha" value={loading ? "…" : stats.staleSources} detail="Manual, rota o atrasada." />
      </section>

      <section className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-foreground">Bandeja de señales</h2>
            <Link to="/signals" className="text-sm text-primary hover:underline">Ver todas</Link>
          </div>
          {loading ? (
            <p className="rounded-xl border p-6 text-muted-foreground">Cargando señales…</p>
          ) : signals.length === 0 ? (
            <p className="rounded-xl border p-6 text-muted-foreground">No hay señales todavía. Registra fuentes o importa items para iniciar cobertura.</p>
          ) : (
            signals.slice(0, 8).map((signal) => <SignalCard key={signal.signal_id || signal.id} signal={signal} />)
          )}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base"><RadioTower className="h-4 w-4" /> Modelo sibling</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p><strong className="text-foreground">Centinelas:</strong> detecta intención pública, señales y asuntos en desarrollo.</p>
              <p><strong className="text-foreground">MoneySweep:</strong> verifica contratos, leyes, pagos, permisos y registros oficiales.</p>
              <p><strong className="text-foreground">Matter ID:</strong> conecta el antes y el después.</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base"><Database className="h-4 w-4" /> Verificación</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>{stats.highConfidence} señales tienen confianza ≥85.</p>
              <p>El lenguaje pre-oficial evita afirmar aprobación, adjudicación o desembolso hasta que exista registro MoneySweep.</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base"><AlertTriangle className="h-4 w-4" /> Próximo cierre</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Automatizar fuentes P0: agendas legislativas, vistas públicas, subastas, juntas, municipios, comunicados y avisos regulatorios.
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base"><Newspaper className="h-4 w-4" /> Publicación</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Las señales pueden convertirse en leads, historias y briefings antes del registro oficial final.
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
