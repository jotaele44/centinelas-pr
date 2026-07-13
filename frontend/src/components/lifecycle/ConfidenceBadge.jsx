import React from "react";
import { Badge } from "@/components/ui/badge";
import { getConfidenceBand } from "@/lib/lifecycle";

const toneClass = {
  strong: "border-emerald-600/30 bg-emerald-600/10 text-emerald-800 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-300",
  high: "border-blue-600/30 bg-blue-600/10 text-blue-800 dark:border-blue-500/40 dark:bg-blue-500/15 dark:text-blue-300",
  medium: "border-amber-600/30 bg-amber-600/10 text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-300",
  watch: "border-slate-600/30 bg-slate-600/10 text-slate-800 dark:border-slate-400/40 dark:bg-slate-400/15 dark:text-slate-300",
  low: "border-orange-600/30 bg-orange-600/10 text-orange-800 dark:border-orange-500/40 dark:bg-orange-500/15 dark:text-orange-300",
  hold: "border-red-600/30 bg-red-600/10 text-red-800 dark:border-red-500/40 dark:bg-red-500/15 dark:text-red-300",
};

export default function ConfidenceBadge({ score }) {
  const band = getConfidenceBand(score);
  return (
    <Badge variant="outline" className={toneClass[band.tone]} title={band.description}>
      {score ?? 0}% · {band.label}
    </Badge>
  );
}
