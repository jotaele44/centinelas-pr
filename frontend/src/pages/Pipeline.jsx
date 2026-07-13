import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Radar, Server } from "lucide-react";
import { getItems, getStatus } from "@/api/pipelineClient";
import DomainBadge, { ALL_DOMAINS, DOMAIN_META } from "@/components/pipeline/DomainBadge";
import EvidenceTierBadge from "@/components/lifecycle/EvidenceTierBadge";
import ConfidenceBadge from "@/components/lifecycle/ConfidenceBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const HUB_REPO = "thehub-pr";

const dispatchTone = {
  ok: "border-emerald-600/30 bg-emerald-600/10 text-emerald-800 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-300",
  failed: "border-red-600/30 bg-red-600/10 text-red-800 dark:border-red-500/40 dark:bg-red-500/15 dark:text-red-300",
  skipped: "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:border-slate-400/40 dark:bg-slate-400/15 dark:text-slate-300",
};

function DispatchChips({ dispatch }) {
  if (!dispatch) {
    return <Badge variant="outline" className="border-slate-400/30 bg-slate-400/10 text-slate-600 dark:border-slate-400/40 dark:bg-slate-400/15 dark:text-slate-300">not yet dispatched</Badge>;
  }
  const tone = dispatchTone[dispatch.status] || dispatchTone.skipped;
  return (
    <div className="flex flex-wrap gap-1.5">
      {(dispatch.dispatched_to || []).map((repo) => (
        <Badge
          key={repo}
          variant="outline"
          className={`${tone} ${repo === HUB_REPO ? "font-bold" : ""}`}
          title={repo === HUB_REPO ? "Hub — every item is logged here" : `Dispatched to ${repo}`}
        >
          {repo === HUB_REPO ? "⬢ hub" : repo.replace(/-pr$/, "")}
        </Badge>
      ))}
    </div>
  );
}

function PipelineItemCard({ item }) {
  const pct = Math.round((Number(item.confidence) || 0) * 100);
  return (
    <Link
      to={`/pipeline/${encodeURIComponent(item.item_id)}`}
      className="block rounded-xl border p-4 transition-colors hover:border-primary/50 hover:bg-muted/40"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate font-semibold text-foreground">{item.title || "(untitled)"}</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">{item.source_name}</p>
        </div>
        <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {(item.labels || []).map((label) => (
          <DomainBadge key={label} domain={label} />
        ))}
        <ConfidenceBadge score={pct} />
        <EvidenceTierBadge tier={item.evidence_tier} />
      </div>
      <div className="mt-3">
        <DispatchChips dispatch={item.dispatch} />
      </div>
    </Link>
  );
}

export default function Pipeline() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState({});
  const [domain, setDomain] = useState("");
  const [loading, setLoading] = useState(true);
  const [reachable, setReachable] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    async function load() {
      const [itemRows, statusRows] = await Promise.all([
        getItems(domain ? { domain } : {}),
        getStatus(),
      ]);
      if (!active) return;
      setItems(Array.isArray(itemRows) ? itemRows : []);
      setStatus(statusRows || {});
      setReachable(Boolean(statusRows) && Object.keys(statusRows || {}).length > 0);
      setLoading(false);
    }
    load();
    return () => {
      active = false;
    };
  }, [domain]);

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-8">
      <section className="rounded-2xl border bg-gradient-to-b from-primary/5 to-background p-6">
        <p className="text-sm font-semibold uppercase tracking-wide text-primary">Universal intake</p>
        <h1 className="mt-1 flex items-center gap-2 text-3xl font-bold text-foreground">
          <Radar className="h-7 w-7 text-primary" aria-hidden="true" /> Pipeline
        </h1>
        <p className="mt-3 max-w-3xl text-muted-foreground">
          Online content classified across six domains and dispatched to the corresponding federation
          repositories. Every item is also logged to thehub-pr regardless of classification.
        </p>
        <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted-foreground">
          <span>Classified: <strong className="text-foreground">{status.classified ?? "…"}</strong></span>
          <span>Dispatched: <strong className="text-foreground">{status.dispatched ?? "…"}</strong></span>
          <span>Queue: <strong className="text-foreground">{status.queue ?? "…"}</strong></span>
        </div>
      </section>

      {!reachable && !loading ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base"><Server className="h-4 w-4" /> Backend not reachable</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            Start the intake API from the repo root:
            <code className="mt-2 block rounded bg-muted px-3 py-2 font-mono text-xs">uvicorn server.backend.main:app --reload --port 8000</code>
          </CardContent>
        </Card>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => setDomain("")}
          className={`rounded-full border px-3 py-1 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${domain === "" ? "border-primary bg-primary/10 font-semibold text-foreground" : "text-muted-foreground hover:text-foreground"}`}
        >
          All
        </button>
        {ALL_DOMAINS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setDomain(d)}
            className={`rounded-full border px-3 py-1 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${domain === d ? "border-primary bg-primary/10 font-semibold text-foreground" : "text-muted-foreground hover:text-foreground"}`}
          >
            {DOMAIN_META[d].label}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="rounded-xl border p-6 text-muted-foreground">Loading items…</p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border p-6 text-muted-foreground">
          No classified items{domain ? ` for ${DOMAIN_META[domain].label}` : ""}. Run the pipeline with{" "}
          <code className="font-mono text-xs">centinelas run</code> to populate.
        </p>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {items.map((item) => (
            <PipelineItemCard key={item.item_id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
