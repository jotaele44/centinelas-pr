import React from "react";
import { Link } from "react-router-dom";
import { CalendarDays, ExternalLink, MapPin } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ConfidenceBadge from "@/components/lifecycle/ConfidenceBadge";
import EvidenceTierBadge from "@/components/lifecycle/EvidenceTierBadge";
import HandoffStatusBadge from "@/components/lifecycle/HandoffStatusBadge";
import { useLanguage } from "@/lib/LanguageContext";

function formatDate(value, locale) {
  if (!value) return null;
  return new Date(value).toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
}

export default function SignalCard({ signal }) {
  const { t, lang } = useLanguage();
  const municipalities = signal.municipalities || [];
  const dateLabel = formatDate(signal.published_at || signal.captured_at, lang === "en" ? "en-US" : "es-PR") || t("Sin fecha");
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
              <span>{signal.beat || t("sin beat")}</span>
              <span>·</span>
              <CalendarDays className="h-4 w-4" aria-hidden="true" />
              <span>{dateLabel}</span>
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
        <p className="text-sm text-foreground">{signal.summary || t("Señal capturada; falta resumen editorial.")}</p>
        <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span>{t("Fuente:")} {signal.source_name || signal.source_id || t("sin fuente asignada")}</span>
          {municipalities.length > 0 ? (
            <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" aria-hidden="true" />{municipalities.join(", ")}</span>
          ) : null}
          {signal.source_url ? (
            <a href={signal.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
              {t("Fuente original")} <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            </a>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
