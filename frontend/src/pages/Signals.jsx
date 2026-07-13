import React, { useEffect, useMemo, useState } from "react";
import SignalCard from "@/components/monitor/SignalCard";
import ListState from "@/components/ListState";
import { loadLifecycle } from "@/lib/appQuery";
import { useLanguage } from "@/lib/LanguageContext";

export default function Signals() {
  const { t } = useLanguage();
  const [signals, setSignals] = useState([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function loadSignals() {
      const { signals: rows, error: loadError } = await loadLifecycle({ signals: true });
      if (!active) return;
      setSignals(rows);
      setError(loadError);
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
        <h1 className="text-3xl font-bold text-foreground">{t("Bandeja de señales")}</h1>
        <p className="mt-2 text-muted-foreground">{t("Información que aparece antes de oficializarse como contrato, ley, pago, permiso, auditoría o expediente.")}</p>
      </div>
      <div className="grid gap-3 md:grid-cols-[1fr_260px]">
        <label className="space-y-1 text-sm font-medium text-foreground">
          {t("Buscar señales")}
          <input value={query} onChange={(event) => setQuery(event.target.value)} className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" placeholder={t("agencia, municipio, RFP, vista, contrato…")} />
        </label>
        <label className="space-y-1 text-sm font-medium text-foreground">
          {t("Handoff")}
          <select value={status} onChange={(event) => setStatus(event.target.value)} className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <option value="all">{t("Todos")}</option>
            <option value="watching">{t("En observación")}</option>
            <option value="candidate">{t("Candidato")}</option>
            <option value="ready_for_moneysweep">{t("Listo para MoneySweep")}</option>
            <option value="matched_to_moneysweep">{t("Vinculado")}</option>
          </select>
        </label>
      </div>
      <div className="space-y-4">
        <ListState
          loading={loading}
          error={error}
          empty={filtered.length === 0}
          loadingLabel="Cargando señales…"
          emptyMessage="No hay señales con esos criterios."
        >
          {filtered.map((signal) => <SignalCard key={signal.signal_id || signal.id} signal={signal} />)}
        </ListState>
      </div>
    </div>
  );
}
