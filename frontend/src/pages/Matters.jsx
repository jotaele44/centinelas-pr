import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ConfidenceBadge from "@/components/lifecycle/ConfidenceBadge";
import HandoffStatusBadge from "@/components/lifecycle/HandoffStatusBadge";
import ListState from "@/components/ListState";
import { getLifecycleStage, isReadyForMoneySweep } from "@/lib/lifecycle";
import { loadLifecycle } from "@/lib/appQuery";
import { useLanguage } from "@/lib/LanguageContext";

export default function Matters() {
  const { t } = useLanguage();
  const [matters, setMatters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function loadMatters() {
      const { matters: rows, error: loadError } = await loadLifecycle({ matters: true });
      if (!active) return;
      setMatters(rows);
      setError(loadError);
      setLoading(false);
    }
    loadMatters();
    return () => {
      active = false;
    };
  }, []);

  const sorted = useMemo(() => [...matters].sort((a, b) => Number(b.confidence_score || 0) - Number(a.confidence_score || 0)), [matters]);

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-foreground">{t("Asuntos públicos")}</h1>
        <p className="mt-2 text-muted-foreground">{t("Objeto compartido entre Centinelas y MoneySweep. Une la señal temprana con el registro oficial posterior.")}</p>
      </div>
      <ListState
        loading={loading}
        error={error}
        empty={sorted.length === 0}
        loadingLabel="Cargando asuntos…"
        emptyMessage="No hay asuntos todavía. Registra señales o importa items para iniciar cobertura."
      >
      <div className="grid gap-4">
        {sorted.map((matter) => {
          const stage = getLifecycleStage(matter.status_lifecycle);
          const handoff = isReadyForMoneySweep(matter) ? "ready_for_moneysweep" : "watching";
          return (
            <Card key={matter.matter_id || matter.id}>
              <CardHeader>
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <CardTitle className="text-lg">
                      <Link to={`/matters/${encodeURIComponent(matter.matter_id || matter.id)}`} className="hover:underline">
                        {matter.title}
                      </Link>
                    </CardTitle>
                    <p className="mt-2 text-sm text-muted-foreground">{matter.matter_type || "matter"} · {t(stage.label)} · {matter.matter_id}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <ConfidenceBadge score={matter.confidence_score} />
                    <HandoffStatusBadge status={handoff} />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm text-muted-foreground md:grid-cols-3">
                <div><span className="font-medium text-foreground">{t("Primer visto:")}</span> {matter.first_seen_at || t("sin fecha")}</div>
                <div><span className="font-medium text-foreground">{t("Fuentes:")}</span> {matter.source_count || 0}</div>
                <div><span className="font-medium text-foreground">MoneySweep:</span> {(matter.moneysweep_record_ids || []).length} {t("record(s)")}</div>
              </CardContent>
            </Card>
          );
        })}
      </div>
      </ListState>
    </div>
  );
}
