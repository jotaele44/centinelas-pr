import React from "react";
import { federationTone } from "@pr-federation/react";
import { useLanguage } from "@/lib/LanguageContext";

const labels = {
  not_ready: "No listo",
  watching: "En observación",
  candidate: "Candidato",
  ready_for_moneysweep: "Listo para MoneySweep",
  matched_to_moneysweep: "Vinculado",
  archived: "Archivado",
};

// Map local handoff statuses onto the canonical federation status vocabulary.
// Colors now come from the shared design system's `.fd-status` tokens
// (@pr-federation/react/styles.css) instead of hard-coded Tailwind classes.
const TONE_ROLE = {
  not_ready: "neutral",
  watching: "warning",
  candidate: "info",
  ready_for_moneysweep: "process",
  matched_to_moneysweep: "success",
  archived: "neutral",
};

export default function HandoffStatusBadge({ status = "watching" }) {
  const { t } = useLanguage();
  const { className: fdClass, ...toneAttrs } = federationTone(TONE_ROLE[status] || "neutral");
  return (
    <span className={`${fdClass} whitespace-nowrap`} {...toneAttrs}>
      {labels[status] ? t(labels[status]) : status}
    </span>
  );
}
