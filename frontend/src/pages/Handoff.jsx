import React, { useEffect, useMemo, useState } from "react";
import { createHandoff, getHandoffs } from "@/api/pipelineClient";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ConfidenceBadge from "@/components/lifecycle/ConfidenceBadge";
import DomainBadge from "@/components/pipeline/DomainBadge";
import ListState from "@/components/ListState";

const TARGETS = [
  { id: "spiderweb-pr", label: "Spiderweb" },
  { id: "aguayluz-pr", label: "Agua y Luz" },
  { id: "moneysweep-pr", label: "Moneysweep" },
  { id: "skywatcher-pr", label: "Skywatcher" },
];

function latestAttempts(item) {
  const receipts = item.handoffs || [];
  return receipts.length ? receipts[receipts.length - 1].attempts || [] : [];
}

export default function Handoff() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState({});
  const [actions, setActions] = useState({});

  const load = async () => {
    setLoading(true);
    const rows = await getHandoffs();
    if (!Array.isArray(rows)) {
      setError("No se pudo cargar el API de handoff.");
      setItems([]);
    } else {
      setError(null);
      setItems(rows);
    }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const deliveredCount = useMemo(
    () => items.filter((item) => latestAttempts(item).some((a) => a.status === "delivered")).length,
    [items],
  );

  const toggle = (itemId, target) => {
    setSelected((current) => {
      const next = new Set(current[itemId] || []);
      if (next.has(target)) next.delete(target); else next.add(target);
      return { ...current, [itemId]: [...next] };
    });
  };

  const send = async (item) => {
    const targets = selected[item.item_id] || [];
    if (!targets.length) return;
    setActions((current) => ({ ...current, [item.item_id]: { status: "sending" } }));
    try {
      const receipt = await createHandoff(item.item_id, targets);
      setActions((current) => ({ ...current, [item.item_id]: receipt }));
      await load();
    } catch (err) {
      setActions((current) => ({
        ...current,
        [item.item_id]: { status: "failed", error: err.message },
      }));
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-8">
      <div>
        <h1 className="text-3xl font-bold text-foreground">Handoff</h1>
        <p className="mt-2 text-muted-foreground">
          Entrega señales clasificadas a los repositorios consumidores y conserva un recibo por destino.
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          {items.length} clasificadas · {deliveredCount} con entrega confirmada
        </p>
      </div>

      <ListState loading={loading} error={error} empty={!items.length}
        loadingLabel="Cargando señales clasificadas…"
        emptyMessage="No hay señales clasificadas. Ejecuta el pipeline primero.">
        <div className="grid gap-4">
          {items.map((item) => {
            const attempts = latestAttempts(item);
            const action = actions[item.item_id];
            return (
              <Card key={item.item_id}>
                <CardHeader>
                  <CardTitle className="text-lg">{item.title || "(sin título)"}</CardTitle>
                  <div className="flex flex-wrap gap-2">
                    {(item.labels || []).map((label) => <DomainBadge key={label} domain={label} />)}
                    <ConfidenceBadge score={Math.round((item.confidence || 0) * 100)} />
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">{item.source_name} · {item.item_id}</p>
                  <fieldset>
                    <legend className="mb-2 text-sm font-medium">Destinos</legend>
                    <div className="flex flex-wrap gap-2">
                      {TARGETS.map((target) => (
                        <label key={target.id} className="flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                          <input type="checkbox"
                            checked={(selected[item.item_id] || []).includes(target.id)}
                            onChange={() => toggle(item.item_id, target.id)} />
                          {target.label}
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  {attempts.length > 0 && (
                    <div className="flex flex-wrap gap-2 text-xs">
                      {attempts.map((attempt) => (
                        <span key={`${attempt.target}-${attempt.attempted_at}`}
                          className="rounded-full border px-3 py-1">
                          {attempt.target.replace(/-pr$/, "")}: {attempt.status}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="flex items-center gap-3 border-t pt-4">
                    <Button type="button"
                      disabled={action?.status === "sending" || !(selected[item.item_id] || []).length}
                      onClick={() => send(item)}>
                      {action?.status === "sending" ? "Entregando…" : "Entregar"}
                    </Button>
                    {action?.error && <span role="alert" className="text-sm text-destructive">{action.error}</span>}
                    {action?.status === "delivered" && <span className="text-sm text-muted-foreground">Entrega confirmada.</span>}
                    {action?.status === "partial" && <span className="text-sm text-muted-foreground">Entrega parcial; reintenta los destinos fallidos.</span>}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </ListState>
    </div>
  );
}
