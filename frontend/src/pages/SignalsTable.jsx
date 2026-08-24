import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import ConfidenceBadge from "@/components/lifecycle/ConfidenceBadge";
import HandoffStatusBadge from "@/components/lifecycle/HandoffStatusBadge";
import ListState from "@/components/ListState";
import { getLifecycleStage } from "@/lib/lifecycle";
import { loadLifecycle } from "@/lib/appQuery";
import { useLanguage } from "@/lib/LanguageContext";

function formatDate(value, locale) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
  } catch (_error) {
    return value;
  }
}

export default function SignalsTable() {
  const { t, lang } = useLanguage();
  const [signals, setSignals] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function load() {
      const { signals: rows, error: loadError } = await loadLifecycle({ signals: true });
      if (!active) return;
      setSignals(rows);
      setError(loadError);
      setLoading(false);
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const normalized = query.toLowerCase().trim();
    if (!normalized) return signals;
    return signals.filter((signal) => [signal.title, signal.summary, signal.beat, signal.signal_type, signal.source_name]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalized)));
  }, [query, signals]);

  const locale = lang === "en" ? "en-US" : "es-PR";

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground">{t("Señales — vista de tabla")}</h1>
          <p className="mt-2 text-muted-foreground">{t("Todas las señales pre-oficiales en una sola pantalla. Cada fila enlaza a su asunto.")}</p>
        </div>
        <Link to="/signals" className="text-sm text-primary hover:underline">{t("Ver como tarjetas")}</Link>
      </div>

      <label className="block max-w-xl space-y-1 text-sm font-medium text-foreground">
        {t("Buscar señales")}
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder={t("agencia, municipio, RFP, vista, contrato…")}
        />
      </label>

      <ListState loading={loading} error={error} empty={filtered.length === 0} loadingLabel="Cargando señales…" emptyMessage="No hay señales con esos criterios.">
        <div className="overflow-x-auto rounded-xl border border-border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50 text-left">
                <th className="px-4 py-3 font-semibold">{t("Título")}</th>
                <th className="px-4 py-3 font-semibold">{t("Tipo")}</th>
                <th className="px-4 py-3 font-semibold">{t("Beat")}</th>
                <th className="px-4 py-3 font-semibold">{t("Etapa")}</th>
                <th className="px-4 py-3 font-semibold">{t("Confianza")}</th>
                <th className="px-4 py-3 font-semibold">{t("Handoff")}</th>
                <th className="px-4 py-3 font-semibold whitespace-nowrap">{t("Capturada")}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((signal) => {
                const stage = getLifecycleStage(signal.signal_stage);
                return (
                  <tr key={signal.signal_id || signal.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 max-w-md">
                      <Link to={`/matters/${encodeURIComponent(signal.matter_id || signal.id)}`} className="font-medium text-primary hover:underline line-clamp-1">
                        {signal.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{signal.signal_type || "signal"}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{signal.beat || t("sin beat")}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{t(stage.label)}</td>
                    <td className="px-4 py-3 whitespace-nowrap"><ConfidenceBadge score={signal.confidence_score} /></td>
                    <td className="px-4 py-3 whitespace-nowrap"><HandoffStatusBadge status={signal.handoff_status} /></td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{formatDate(signal.captured_at || signal.published_at, locale)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </ListState>
    </div>
  );
}
