import React, { useCallback, useEffect, useState } from "react";
import { Droplets, RefreshCw, Server } from "lucide-react";
import { getWaterDisruptionConsole } from "@/api/pipelineClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function WaterDisruption() {
  const [consoleState, setConsoleState] = useState({ loading: true, available: false, url: "" });

  const loadConsole = useCallback(async () => {
    setConsoleState((state) => ({ ...state, loading: true }));
    const result = await getWaterDisruptionConsole();
    setConsoleState({ loading: false, ...result });
  }, []);

  useEffect(() => {
    loadConsole();
  }, [loadConsole]);

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-6">
      <div className="mb-4">
        <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
          <Droplets className="h-6 w-6 text-primary" aria-hidden="true" />
          Water Disruption Shadow Queue
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Shadow-mode evidence, candidates, delivery outbox, and provenance. Live alerts and production promotion remain disabled.
        </p>
      </div>

      {consoleState.loading ? (
        <p role="status" className="rounded-lg border p-6 text-sm text-muted-foreground">
          Checking water disruption console availability…
        </p>
      ) : consoleState.available ? (
        <iframe
          src={consoleState.url}
          title="Water disruption shadow console"
          className="min-h-[70vh] w-full rounded-lg border bg-background"
        />
      ) : (
        <Card role="alert">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="h-4 w-4" aria-hidden="true" />
              Water disruption console unavailable
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-muted-foreground">
            <p>The backend console could not be loaded. No alert or queue data has been changed.</p>
            <button
              type="button"
              onClick={loadConsole}
              aria-label="Retry loading water disruption console"
              className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Retry
            </button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
