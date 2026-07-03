import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { appClient } from "@/api/appClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ConfidenceBadge from "@/components/lifecycle/ConfidenceBadge";
import HandoffStatusBadge from "@/components/lifecycle/HandoffStatusBadge";
import { getLifecycleStage, isReadyForMoneySweep, mapLegacyLawToMatter } from "@/lib/lifecycle";

async function safeList(entityName, sort = "-first_seen_at", limit = 200) {
  const entity = appClient.entities?.[entityName];
  if (!entity?.list) return [];
  try {
    return await entity.list(sort, limit);
  } catch (_error) {
    return [];
  }
}

export default function Matters() {
  const [matters, setMatters] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function loadMatters() {
      const [matterRows, legacyLaws] = await Promise.all([
        safeList("Matter", "-first_seen_at", 200),
        safeList("Law", "-last_action_date", 100),
      ]);
      if (!active) return;
      setMatters(matterRows.length > 0 ? matterRows : legacyLaws.map(mapLegacyLawToMatter));
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
        <h1 className="text-3xl font-bold text-foreground">Asuntos públicos</h1>
        <p className="mt-2 text-muted-foreground">Objeto compartido entre Centinelas y MoneySweep. Une la señal temprana con el registro oficial posterior.</p>
      </div>
      {loading ? <p className="rounded-xl border p-6 text-muted-foreground">Cargando asuntos…</p> : null}
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
                    <p className="mt-2 text-sm text-muted-foreground">{matter.matter_type || "matter"} · {stage.label} · {matter.matter_id}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <ConfidenceBadge score={matter.confidence_score} />
                    <HandoffStatusBadge status={handoff} />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="grid gap-3 text-sm text-muted-foreground md:grid-cols-3">
                <div><span className="font-medium text-foreground">Primer visto:</span> {matter.first_seen_at || "sin fecha"}</div>
                <div><span className="font-medium text-foreground">Fuentes:</span> {matter.source_count || 0}</div>
                <div><span className="font-medium text-foreground">MoneySweep:</span> {(matter.moneysweep_record_ids || []).length} record(s)</div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
