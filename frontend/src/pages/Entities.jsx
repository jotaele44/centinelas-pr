import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, User, Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import ListState from "@/components/ListState";
import { loadLifecycle, deriveEntities } from "@/lib/appQuery";
import { useLanguage } from "@/lib/LanguageContext";

const TYPE_ICON = { agency: Building2, person: User, organization: Users, entity: Users };
const TYPE_LABEL = { agency: "Agencia", person: "Persona", organization: "Organización", entity: "Entidad" };

export default function Entities() {
  const { t } = useLanguage();
  const [entities, setEntities] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function load() {
      const { signals, matters, error: loadError } = await loadLifecycle({ signals: true, matters: true });
      if (!active) return;
      setEntities(deriveEntities(signals, matters));
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
    if (!normalized) return entities;
    return entities.filter((entity) => entity.name.toLowerCase().includes(normalized));
  }, [query, entities]);

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-foreground">{t("Entidades")}</h1>
        <p className="mt-2 text-muted-foreground">{t("Agencias, personas y organizaciones mencionadas en las señales y asuntos monitoreados.")}</p>
      </div>

      <label className="block max-w-xl space-y-1 text-sm font-medium text-foreground">
        {t("Buscar entidad")}
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="w-full rounded-lg border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          placeholder={t("agencia, persona, organización…")}
        />
      </label>

      <ListState loading={loading} error={error} empty={filtered.length === 0} loadingLabel="Cargando entidades…" emptyMessage="No hay entidades mencionadas en las señales todavía.">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((entity) => {
            const Icon = TYPE_ICON[entity.type] || Users;
            return (
              <Link key={entity.slug} to={`/entidad/${encodeURIComponent(entity.slug)}`} className="block">
                <Card className="h-full transition-colors hover:border-primary/50">
                  <CardHeader>
                    <div className="flex items-start justify-between gap-3">
                      <CardTitle className="flex items-center gap-2 text-base">
                        <Icon className="h-4 w-4 text-primary shrink-0" aria-hidden="true" />
                        <span className="line-clamp-2">{entity.name}</span>
                      </CardTitle>
                      <Badge variant="outline">{t(TYPE_LABEL[entity.type] || TYPE_LABEL.entity)}</Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="text-sm text-muted-foreground">
                    {entity.mentionCount} {t("menciones")} · {entity.signalIds.length} {t("señales")}
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
      </ListState>
    </div>
  );
}
