import React from "react";
import { GitBranch, Check, X, Circle } from "lucide-react";
import { useLanguage } from "@/lib/LanguageContext";

const STAGES = [
  { key: "Radicada", label: "Radicación", description: "Proyecto presentado oficialmente" },
  { key: "En comisión", label: "En comisión", description: "Revisión y debate en comisión legislativa" },
  { key: "En conferencia", label: "En conferencia", description: "Discusión entre ambas cámaras" },
  { key: "Aprobada por el Senado", label: "Aprobada por el Senado", description: "Votación favorable del Senado" },
  { key: "Aprobada por la Cámara", label: "Aprobada por la Cámara", description: "Votación favorable de la Cámara" },
  { key: "Aprobada", label: "Aprobada", description: "Aprobación final legislativa" },
  { key: "Ley", label: "Ley firmada", description: "Firmada y convertida en ley" },
];

export default function LawTimeline({ law }) {
  const { t } = useLanguage();
  const isRejected = law.status === "Rechazada";
  const currentStageIndex = STAGES.findIndex((s) => s.key === law.status);

  return (
    <div className="bg-card rounded-2xl border border-border p-6">
      <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <GitBranch className="w-5 h-5 text-primary" aria-hidden="true" />
        {t("Línea de tiempo del proceso legislativo")}
      </h2>
      <div className="relative">
        {STAGES.map((stage, i) => {
          const isPassed = !isRejected && i <= currentStageIndex;
          const isCurrent = !isRejected && i === currentStageIndex;
          const date =
            i === 0
              ? law.submission_date
              : isCurrent
              ? law.last_action_date
              : null;

          return (
            <div key={stage.key} className="flex gap-4 pb-6 last:pb-0 relative">
              {i < STAGES.length - 1 && (
                <div
                  className={`absolute left-4 top-9 w-0.5 h-full ${
                    isPassed ? "bg-primary" : "bg-border"
                  }`}
                />
              )}
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 z-10 ${
                  isPassed
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground border border-border"
                }`}
              >
                {isPassed ? <Check className="w-4 h-4" aria-hidden="true" /> : <Circle className="w-3 h-3" aria-hidden="true" />}
              </div>
              <div className="pt-1">
                <p className={`font-medium ${isPassed ? "text-foreground" : "text-muted-foreground"}`}>
                  {t(stage.label)}
                </p>
                <p className="text-sm text-muted-foreground">{t(stage.description)}</p>
                {date && (
                  <p className="text-xs text-primary mt-1 font-medium">
                    {new Date(date).toLocaleDateString("es-PR", {
                      year: "numeric",
                      month: "long",
                      day: "numeric",
                    })}
                  </p>
                )}
                {isCurrent && (
                  <span className="inline-block mt-1 text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-full font-medium">
                    {t("Etapa actual")}
                  </span>
                )}
              </div>
            </div>
          );
        })}
        {isRejected && (
          <div className="flex gap-4 relative">
            <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 z-10 bg-red-500 text-white">
              <X className="w-4 h-4" aria-hidden="true" />
            </div>
            <div className="pt-1">
              <p className="font-medium text-red-600 dark:text-red-400">{t("Rechazada")}</p>
              <p className="text-sm text-muted-foreground">{t("El proyecto no fue aprobado")}</p>
              {law.last_action_date && (
                <p className="text-xs text-red-600 mt-1 font-medium">
                  {new Date(law.last_action_date).toLocaleDateString("es-PR", {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}