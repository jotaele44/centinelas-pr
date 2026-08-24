import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Building2, User, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import SignalCard from "@/components/monitor/SignalCard";
import { loadLifecycle, deriveEntities } from "@/lib/appQuery";
import { useLanguage } from "@/lib/LanguageContext";

const TYPE_ICON = { agency: Building2, person: User, organization: Users, entity: Users };
const TYPE_LABEL = { agency: "Agencia", person: "Persona", organization: "Organización", entity: "Entidad" };

export default function EntityDetail() {
  const { slug } = useParams();
  const entitySlug = decodeURIComponent(slug || "");
  const { t } = useLanguage();
  const [signals, setSignals] = useState([]);
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    async function load() {
      const { signals: signalRows, matters, error: loadError } = await loadLifecycle({ signals: true, matters: true });
      if (!active) return;
      setSignals(signalRows);
      setEntities(deriveEntities(signalRows, matters));
      setError(loadError);
      setLoading(false);
    }
    load();
    return () => {
      active = false;
    };
  }, []);

  const entity = useMemo(() => entities.find((item) => item.slug === entitySlug), [entities, entitySlug]);
  const linkedSignals = useMemo(() => {
    if (!entity) return [];
    const ids = new Set(entity.signalIds);
    return signals.filter((signal) => ids.has(signal.signal_id || signal.id));
  }, [entity, signals]);

  if (loading) {
    return <div className="max-w-7xl mx-auto px-4 py-8"><p role="status" aria-live="polite" className="rounded-xl border p-6 text-muted-foreground">{t("Cargando entidad…")}</p></div>;
  }
  if (error) {
    return <div className="max-w-7xl mx-auto px-4 py-8"><p role="alert" className="rounded-xl border border-destructive/40 bg-destructive/5 p-6 text-sm text-foreground">{t("No se pudo cargar la entidad. Revisa la conexión con el almacén de datos e inténtalo de nuevo.")}</p></div>;
  }
  if (!entity) {
    return <div className="max-w-7xl mx-auto px-4 py-8"><p className="rounded-xl border p-6 text-muted-foreground">{t("Entidad no encontrada.")}</p></div>;
  }

  const Icon = TYPE_ICON[entity.type] || Users;

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
      <Link to="/entidades" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> {t("Volver a entidades")}
      </Link>

      <section className="rounded-2xl border p-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary shrink-0">
              <Icon className="h-6 w-6" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-foreground">{entity.name}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {entity.mentionCount} {t("menciones")} · {linkedSignals.length} {t("señales")}
              </p>
            </div>
          </div>
          <Badge variant="outline">{t(TYPE_LABEL[entity.type] || TYPE_LABEL.entity)}</Badge>
        </div>
      </section>

      <div className="space-y-4">
        <h2 className="text-xl font-semibold text-foreground">{t("Señales relacionadas")}</h2>
        {linkedSignals.length === 0 ? (
          <p className="rounded-xl border p-6 text-muted-foreground">{t("No hay señales vinculadas.")}</p>
        ) : (
          linkedSignals.map((signal) => <SignalCard key={signal.signal_id || signal.id} signal={signal} />)
        )}
      </div>
    </div>
  );
}
