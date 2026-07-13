import React, { useEffect, useMemo, useState } from "react";
import { appClient } from "@/api/appClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import HandoffStatusBadge from "@/components/lifecycle/HandoffStatusBadge";
import ConfidenceBadge from "@/components/lifecycle/ConfidenceBadge";
import ListState from "@/components/ListState";
import { HANDOFF_TRIGGERS, isReadyForMoneySweep } from "@/lib/lifecycle";
import { loadLifecycle } from "@/lib/appQuery";

export default function Handoff() {
  const [matters, setMatters] = useState([]);
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionState, setActionState] = useState({});

  useEffect(() => {
    let active = true;
    async function loadHandoff() {
      const { matters: matterRows, signals: signalRows, error: loadError } =
        await loadLifecycle({ matters: true, signals: true });
      if (!active) return;
      setMatters(matterRows);
      setSignals(signalRows);
      setError(loadError);
      setLoading(false);
    }
    loadHandoff();
    return () => {
      active = false;
    };
  }, []);

  const candidates = useMemo(() => matters
    .map((matter) => ({
      matter,
      signals: signals.filter((signal) => signal.matter_id === matter.matter_id),
    }))
    .filter(({ matter, signals: linkedSignals }) => isReadyForMoneySweep(matter, linkedSignals)), [matters, signals]);

  const runHandoffAction = async (action, matter, linkedSignals) => {
    const key = matter.matter_id || matter.id;
    setActionState((current) => ({ ...current, [key]: `${action}_running` }));
    try {
      const candidatePayload = {
        matter_id: matter.matter_id,
        candidate_id: matter.last_handoff_candidate_id || `manual-${matter.matter_id}`,
        official_record: {
          matter_id: matter.matter_id,
          title: matter.title,
          official_identifier: matter.official_identifier || "",
          official_source_url: matter.official_source_url || "",
          linked_signal_ids: linkedSignals.map((signal) => signal.signal_id || signal.id).filter(Boolean),
        },
      };

      if (action === "evaluate") {
        await appClient.functions.invoke("evaluateHandoffCandidate", { matter_id: matter.matter_id });
      } else if (action === "accept") {
        await appClient.functions.invoke("acceptHandoffCandidate", candidatePayload);
      } else if (action === "reject") {
        await appClient.functions.invoke("rejectHandoffCandidate", {
          matter_id: matter.matter_id,
          reason: "Reviewer rejected automatic handoff candidate from Centinelas UI.",
        });
      }

      setActionState((current) => ({ ...current, [key]: `${action}_ok` }));
    } catch (error) {
      setActionState((current) => ({ ...current, [key]: `${action}_failed: ${error.message}` }));
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-foreground">Handoff hacia MoneySweep</h1>
        <p className="mt-2 text-muted-foreground">Asuntos donde Centinelas detectó señal de oficialización y debe crearse o vincularse un registro canónico posterior.</p>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-base">Disparadores aceptados</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap gap-2 text-sm text-muted-foreground">
          {HANDOFF_TRIGGERS.map((trigger) => <span key={trigger} className="rounded-full border px-3 py-1">{trigger}</span>)}
        </CardContent>
      </Card>
      <ListState
        loading={loading}
        error={error}
        empty={candidates.length === 0}
        loadingLabel="Evaluando candidatos…"
        emptyMessage="No hay candidatos listos. Esto es correcto si aún no existe identificador oficial, contrato, ley, pago, permiso, auditoría o docket."
      >
      <div className="grid gap-4">
        {candidates.map(({ matter, signals: linkedSignals }) => (
          <Card key={matter.matter_id || matter.id}>
            <CardHeader>
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <CardTitle className="text-lg">{matter.title}</CardTitle>
                  <p className="mt-2 break-all text-sm text-muted-foreground">{matter.matter_id}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <ConfidenceBadge score={matter.confidence_score} />
                  <HandoffStatusBadge status="ready_for_moneysweep" />
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-muted-foreground">
              <div className="grid gap-3 md:grid-cols-3">
                <div><span className="font-medium text-foreground">Tipo:</span> {matter.matter_type}</div>
                <div><span className="font-medium text-foreground">Señales:</span> {linkedSignals.length}</div>
                <div><span className="font-medium text-foreground">Oficial:</span> {matter.official_identifier || matter.official_source_url || "requiere vinculación"}</div>
              </div>
              <div className="flex flex-wrap gap-2 border-t pt-4">
                <Button type="button" variant="outline" size="sm" onClick={() => runHandoffAction("evaluate", matter, linkedSignals)}>Evaluar</Button>
                <Button type="button" size="sm" onClick={() => runHandoffAction("accept", matter, linkedSignals)}>Aceptar / crear registro</Button>
                <Button type="button" variant="destructive" size="sm" onClick={() => runHandoffAction("reject", matter, linkedSignals)}>Rechazar</Button>
                {actionState[matter.matter_id || matter.id] && (
                  <span className="self-center text-xs text-muted-foreground">{actionState[matter.matter_id || matter.id]}</span>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      </ListState>
    </div>
  );
}
