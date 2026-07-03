import React, { useEffect, useMemo, useState } from "react";
import { appClient } from "@/api/appClient";
import SignalCard from "@/components/monitor/SignalCard";
import { mapLegacyLawToSignal } from "@/lib/lifecycle";

async function safeList(entityName, sort = "-captured_at", limit = 200) {
  const entity = appClient.entities?.[entityName];
  if (!entity?.list) return [];
  try {
    return await entity.list(sort, limit);
  } catch (_error) {
    return [];
  }
}

export default function Signals() {
  const [signals, setSignals] = useState([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function loadSignals() {
      const [signalRows, legacyLaws] = await Promise.all([
        safeList("Signal", "-captured_at", 200),
        safeList("Law", "-last_action_date", 100),
      ]);
      if (!active) return;
      setSignals(signalRows.length > 0 ? signalRows : legacyLaws.map(mapLegacyLawToSignal));
      setLoading(false);
    }
    loadSignals();
    return () => {
      active = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const normalized = query.toLowerCase().trim();
    return signals.filter((signal) => {
      const matchesQuery = !normalized || [signal.title, signal.summary, signal.beat, signal.source_name]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalized));
      const matchesStatus = status === "all" || signal.handoff_status === status;
      return matchesQuery && matchesStatus;
    });
  }, [query, signals, status]);

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-foreground">Bandeja de señales</h1>
        <p className="mt-2 text-muted-foreground">Información que aparece antes de oficializarse como contrato, ley, pago, permiso, auditoría o expediente.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-[1fr_260px]">
        <label className="space-y-1 text-sm font-medium text-foreground">
          Buscar señales
          <input value={query} onChange={(event) => setQuery(event.target.value)} className="w-full rounded-lg border bg-background px-3 py-2 text-sm" placeholder="agencia, municipio, RFP, vista, contrato…" />
        </label>
        <label className="space-y-1 text-sm font-medium text-foreground">
          Handoff
          <select value={status} onChange={(event) => setStatus(event.target.value)} className="w-full rounded-lg border bg-background px-3 py-2 text-sm">
            <option value="all">Todos</option>
            <option value="watching">En observación</option>
            <option value="candidate">Candidato</option>
            <option value="ready_for_moneysweep">Listo para MoneySweep</option>
            <option value="matched_to_moneysweep">Vinculado</option>
          </select>
        </label>
      </div>
      <div className="space-y-4">
        {loading ? <p className="rounded-xl border p-6 text-muted-foreground">Cargando señales…</p> : null}
        {!loading && filtered.length === 0 ? <p className="rounded-xl border p-6 text-muted-foreground">No hay señales con esos criterios.</p> : null}
        {filtered.map((signal) => <SignalCard key={signal.signal_id || signal.id} signal={signal} />)}
      </div>
    </div>
  );
}
