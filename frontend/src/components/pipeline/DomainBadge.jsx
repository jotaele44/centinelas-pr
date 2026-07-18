import React from "react";
import { Badge } from "@/components/ui/badge";

// Maps each universal DomainLabel (from the Python backend's DomainLabel enum)
// to a color treatment + the sibling repo it routes to. Mirrors the backend's
// LABEL_TO_REPO mapping in src/centinelas/classify/labels.py.
export const DOMAIN_META = {
  ENVIRONMENTAL: { label: "Environmental", repo: "aguayluz-pr", tone: "border-emerald-600/30 bg-emerald-600/10 text-emerald-800 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-300" },
  FINANCIAL: { label: "Financial", repo: "moneysweep-pr", tone: "border-green-700/30 bg-green-700/10 text-green-900 dark:border-green-500/40 dark:bg-green-500/15 dark:text-green-300" },
  POLITICAL: { label: "Political", repo: "moneysweep-pr", tone: "border-indigo-600/30 bg-indigo-600/10 text-indigo-800 dark:border-indigo-500/40 dark:bg-indigo-500/15 dark:text-indigo-300" },
  GEO_GEOLOGY: { label: "Geo/Geology", repo: "spiderweb-pr", tone: "border-amber-700/30 bg-amber-700/10 text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-300" },
  ANOMALOUS: { label: "Anomalous", repo: "ovnis-pr", tone: "border-violet-600/30 bg-violet-600/10 text-violet-800 dark:border-violet-500/40 dark:bg-violet-500/15 dark:text-violet-300" },
  MILITARY_AEROSPACE: { label: "Military/Aerospace", repo: "skywatcher-pr", tone: "border-sky-700/30 bg-sky-700/10 text-sky-900 dark:border-sky-500/40 dark:bg-sky-500/15 dark:text-sky-300" },
  UNCLASSIFIED: { label: "Unclassified", repo: null, tone: "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:border-slate-400/40 dark:bg-slate-400/15 dark:text-slate-300" },
};

export const ALL_DOMAINS = [
  "ENVIRONMENTAL",
  "FINANCIAL",
  "POLITICAL",
  "GEO_GEOLOGY",
  "ANOMALOUS",
  "MILITARY_AEROSPACE",
  "UNCLASSIFIED",
];

export default function DomainBadge({ domain }) {
  const meta = DOMAIN_META[domain] || DOMAIN_META.UNCLASSIFIED;
  const title = meta.repo ? `Routes to ${meta.repo}` : "No domain match — logged to thehub-pr only";
  return (
    <Badge variant="outline" className={meta.tone} title={title}>
      {meta.label}
    </Badge>
  );
}
