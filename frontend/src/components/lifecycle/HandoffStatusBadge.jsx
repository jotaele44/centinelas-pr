import React from "react";
import { Badge } from "@/components/ui/badge";

const labels = {
  not_ready: "No listo",
  watching: "En observación",
  candidate: "Candidato",
  ready_for_moneysweep: "Listo para MoneySweep",
  matched_to_moneysweep: "Vinculado",
  archived: "Archivado",
};

const classNames = {
  ready_for_moneysweep: "border-purple-600/30 bg-purple-600/10 text-purple-800",
  matched_to_moneysweep: "border-emerald-600/30 bg-emerald-600/10 text-emerald-800",
  candidate: "border-blue-600/30 bg-blue-600/10 text-blue-800",
  watching: "border-amber-600/30 bg-amber-600/10 text-amber-800",
  archived: "border-slate-600/30 bg-slate-600/10 text-slate-800",
  not_ready: "border-slate-600/30 bg-slate-600/10 text-slate-800",
};

export default function HandoffStatusBadge({ status = "watching" }) {
  return (
    <Badge variant="outline" className={classNames[status] || classNames.watching}>
      {labels[status] || status}
    </Badge>
  );
}
