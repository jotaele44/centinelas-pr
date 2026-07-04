import React from "react";
import { Badge } from "@/components/ui/badge";
import { getConfidenceBand } from "@/lib/lifecycle";

const toneClass = {
  strong: "border-emerald-600/30 bg-emerald-600/10 text-emerald-800",
  high: "border-blue-600/30 bg-blue-600/10 text-blue-800",
  medium: "border-amber-600/30 bg-amber-600/10 text-amber-800",
  watch: "border-slate-600/30 bg-slate-600/10 text-slate-800",
  low: "border-orange-600/30 bg-orange-600/10 text-orange-800",
  hold: "border-red-600/30 bg-red-600/10 text-red-800",
};

export default function ConfidenceBadge({ score }) {
  const band = getConfidenceBand(score);
  return (
    <Badge variant="outline" className={toneClass[band.tone]} title={band.description}>
      {score ?? 0}% · {band.label}
    </Badge>
  );
}
