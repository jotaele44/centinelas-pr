import React from "react";
import { MATTER_LIFECYCLE_STAGES, getLifecycleStage } from "@/lib/lifecycle";
import { useLanguage } from "@/lib/LanguageContext";

export default function MatterTimeline({ currentStage = "public_signal" }) {
  const { t } = useLanguage();
  const active = getLifecycleStage(currentStage);
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold text-foreground">{t("Línea de vida del asunto")}</h3>
          <p className="text-sm text-muted-foreground">{t("Centinelas detecta intención; MoneySweep verifica ejecución oficial.")}</p>
        </div>
        <span className="text-xs text-muted-foreground">{t("Etapa")} {active.order}/6</span>
      </div>
      <div className="grid gap-3 md:grid-cols-7">
        {MATTER_LIFECYCLE_STAGES.map((stage) => {
          const isReached = stage.order <= active.order;
          const isActive = stage.key === active.key;
          return (
            <div key={stage.key} className={`rounded-lg border p-3 ${isActive ? "border-primary bg-primary/10" : isReached ? "bg-muted/60" : "bg-background"}`}>
              <div className="text-xs font-semibold text-muted-foreground">{t(stage.app)}</div>
              <div className="mt-1 text-sm font-medium text-foreground">{t(stage.label)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
