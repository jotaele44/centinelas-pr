import React from "react";
import { federationTone } from "@pr-federation/react";
import { getConfidenceBand } from "@/lib/lifecycle";
import { useLanguage } from "@/lib/LanguageContext";

// Map this app's confidence tones onto the canonical federation status
// vocabulary. Colors now come from the shared design system's `.fd-status`
// tokens (@pr-federation/react/styles.css) instead of hard-coded Tailwind
// color classes.
const TONE_ROLE = {
  strong: "success",
  high: "info",
  medium: "warning",
  watch: "neutral",
  low: "caution",
  hold: "danger",
};

export default function ConfidenceBadge({ score }) {
  const { t } = useLanguage();
  const band = getConfidenceBand(score);
  const { className: fdClass, ...toneAttrs } = federationTone(TONE_ROLE[band.tone] || "neutral");
  return (
    <span className={`${fdClass} whitespace-nowrap`} title={t(band.description)} {...toneAttrs}>
      {score ?? 0}% · {t(band.label)}
    </span>
  );
}
