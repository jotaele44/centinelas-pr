import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import MatterTimeline from "@/components/lifecycle/MatterTimeline";
import SignalCard from "@/components/monitor/SignalCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ConfidenceBadge from "@/components/lifecycle/ConfidenceBadge";
import HandoffStatusBadge from "@/components/lifecycle/HandoffStatusBadge";
import { isReadyForMoneySweep } from "@/lib/lifecycle";
import { loadLifecycle } from "@/lib/appQuery";

export default function MatterDetail() {
  const { id } = useParams();
  const matterKey = decodeURIComponent(id || "");
  const [matters, setMatters] = useState([]);
  const [signals, setSignals] = useState([]);
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function loadMatter() {
      const { matters: matterRows, signals: signalRows, records: recordRows, error: loadError } =
        await loadLifecycle({ matters: true, signals: true, records: true });
      if (!active) return;
      setMatters(matterRows);
      setSignals(signalRows);
      setRecords(recordRows);
      setError(loadError);
      setLoading(false);
    }
    loadMatter();
    return () => {
      active = false;
    };
  }, []);

  const matter = useMemo(() => matters.find((item) => item.matter_id === matterKey || item.id === matterKey), [matterKey, matters]);
  const linkedSignals = useMemo(() => signals.filter((signal) => signal.matter_id === matterKey || signal.matter_id === matter?.matter_id), [matter?.matter_id, matterKey, signals]);
  const linkedRecords = useMemo(() => records.filter((record) => record.matter_id === matterKey || record.matter_id === matter?.matter_id), [matter?.matter_id, matterKey, records]);

  if (loading) {
    return <div className="max-w-7xl mx-auto px-4 py-8"><p role="status" aria-live="polite" className="rounded-xl border p-6 text-muted-foreground">Cargando asunto…</p></div>;
  }

  if (error) {
    return <div className="max-w-7xl mx-auto px-4 py-8"><p role="alert" className="rounded-xl border border-destructive/40 bg-destructive/5 p-6 text-sm text-foreground">No se pudo cargar el asunto. Revisa la conexión con el almacén de datos e inténtalo de nuevo.</p></div>;
  }

  if (!matter) {
    return <div className="max-w-7xl mx-auto px-4 py-8"><p className="rounded-xl border p-6 text-muted-foreground">Asunto no encontrado.</p></div>;
  }

  const handoffStatus = isReadyForMoneySweep(matter, linkedSignals) ? "ready_for_moneysweep" : "watching";

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
      <section className="rounded-2xl border p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-primary">Matter ID</p>
            <h1 className="mt-1 text-3xl font-bold text-foreground">{matter.title}</h1>
            <p className="mt-2 break-all text-sm text-muted-foreground">{matter.matter_id}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <ConfidenceBadge score={matter.confidence_score} />
            <HandoffStatusBadge status={handoffStatus} />
          </div>
        </div>
      </section>

      <MatterTimeline currentStage={matter.status_lifecycle} />

      <section className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          <h2 className="text-xl font-semibold text-foreground">Señales Centinelas</h2>
          {linkedSignals.length === 0 ? <p className="rounded-xl border p-6 text-muted-foreground">No hay señales vinculadas.</p> : null}
          {linkedSignals.map((signal) => <SignalCard key={signal.signal_id || signal.id} signal={signal} />)}
        </div>
        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Panel MoneySweep</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>Registros oficiales vinculados: {linkedRecords.length}</p>
              <p>Identificador oficial: {matter.official_identifier || "pendiente"}</p>
              <p>URL oficial: {matter.official_source_url ? "capturada" : "pendiente"}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Regla de lenguaje</CardTitle></CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              Mientras no exista registro oficial, describir como anunciado, propuesto, programado, bajo consideración o pendiente de oficialización.
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
