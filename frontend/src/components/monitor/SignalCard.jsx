import React from "react";
import { Link } from "react-router-dom";
import { CalendarDays, ExternalLink, MapPin } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ConfidenceBadge from "@/components/lifecycle/ConfidenceBadge";
import EvidenceTierBadge from "@/components/lifecycle/EvidenceTierBadge";
import HandoffStatusBadge from "@/components/lifecycle/HandoffStatusBadge";

function formatDate(value) {
  if (!value) return "Sin fecha";
  return new Date(value).toLocaleDateString("es-PR", { year: "numeric", month: "short", day: "numeric" });
}

export default function SignalCard({ signal }) {
  const municipalities = signal.municipalities || [];
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <CardTitle className="text-lg leading-snug">
              <Link to={`/matters/${encodeURIComponent(signal.matter_id || signal.id)}`} className="hover:underline">
                {signal.title}
              </Link>
            </CardTitle>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>{signal.signal_type || "signal"}</span>
              <span>·</span>
              <span>{signal.beat || "sin beat"}</span>
              <span>·</span>
              <CalendarDays className="h-4 w-4" />
              <span>{formatDate(signal.published_at || signal.captured_at)}</span>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <ConfidenceBadge score={signal.confidence_score} />
            <EvidenceTierBadge tier={signal.evidence_tier} />
            <HandoffStatusBadge status={signal.handoff_status} />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-foreground">{signal.summary || "Señal capturada; falta resumen editorial."}</p>
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>Fuente: {signal.source_name || signal.source_id || "sin fuente asignada"}</span>
          {municipalities.length > 0 ? (
            <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" />{municipalities.join(", ")}</span>
          ) : null}
          {signal.source_url ? (
            <a href={signal.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
              Fuente original <ExternalLink className="h-3.5 w-3.5" />
            </a>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
