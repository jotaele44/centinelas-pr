import React from "react";
import { Badge } from "@/components/ui/badge";
import { EVIDENCE_TIERS } from "@/lib/lifecycle";

export default function EvidenceTierBadge({ tier = "T4" }) {
  return (
    <Badge variant="outline" title={EVIDENCE_TIERS[tier] || "Sin definición de evidencia"}>
      {tier}
    </Badge>
  );
}
