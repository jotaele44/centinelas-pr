import React, { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import ListState from "@/components/ListState";
import { loadLifecycle } from "@/lib/appQuery";

const seedSources = [
  { name: "Senado de Puerto Rico", source_type: "legislature", coverage_tier: "P0", status: "manual", beat_tags: ["legislature", "hearings", "votes"] },
  { name: "Cámara de Representantes", source_type: "legislature", coverage_tier: "P0", status: "manual", beat_tags: ["legislature", "committees"] },
  { name: "PR.gov", source_type: "central_government", coverage_tier: "P0", status: "manual", beat_tags: ["executive", "agencies"] },
  { name: "ASG / subastas", source_type: "procurement", coverage_tier: "P0", status: "manual", beat_tags: ["contracts", "rfp"] },
  { name: "Municipios de Puerto Rico", source_type: "municipal", coverage_tier: "P0", status: "manual", beat_tags: ["municipal", "agendas"] },
  { name: "Rama Judicial / expedientes", source_type: "court", coverage_tier: "P1", status: "manual", beat_tags: ["courts", "litigation"] },
];

export default function Sources() {
  const [sources, setSources] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function loadSources() {
      const { sources: rows, error: loadError } = await loadLifecycle({ sources: true });
      if (!active) return;
      setSources(rows.length > 0 ? rows : seedSources);
      setError(loadError);
      setLoading(false);
    }
    loadSources();
    return () => {
      active = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const normalized = query.toLowerCase().trim();
    if (!normalized) return sources;
    return sources.filter((source) => [source.name, source.source_type, source.coverage_tier, source.status]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalized)));
  }, [query, sources]);

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-foreground">Registro de fuentes</h1>
        <p className="mt-2 text-muted-foreground">Cobertura upstream: fuentes que anuncian, agendan, notifican o anticipan asuntos antes de oficializarse.</p>
      </div>
      <label className="block max-w-xl space-y-1 text-sm font-medium text-foreground">
        Buscar fuente
        <input value={query} onChange={(event) => setQuery(event.target.value)} className="w-full rounded-lg border bg-background px-3 py-2 text-sm" placeholder="legislatura, municipio, subasta, tribunal…" />
      </label>
      <ListState
        loading={loading}
        error={error}
        empty={filtered.length === 0}
        loadingLabel="Cargando fuentes…"
        emptyMessage="No hay fuentes con esos criterios."
      >
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {filtered.map((source) => (
          <Card key={source.id || source.name}>
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <CardTitle className="text-base">{source.name}</CardTitle>
                <Badge variant="outline">{source.coverage_tier || "P?"}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>{source.source_type || "sin tipo"}</p>
              <p>Estado: <span className="font-medium text-foreground">{source.status || "unknown"}</span></p>
              <p>Último éxito: {source.last_success_at || "pendiente"}</p>
              <div className="flex flex-wrap gap-2">
                {(source.beat_tags || []).map((tag) => <Badge key={tag} variant="secondary">{tag}</Badge>)}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      </ListState>
    </div>
  );
}
