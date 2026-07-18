import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { getItem } from "@/api/pipelineClient";
import DomainBadge from "@/components/pipeline/DomainBadge";
import EvidenceTierBadge from "@/components/lifecycle/EvidenceTierBadge";
import ConfidenceBadge from "@/components/lifecycle/ConfidenceBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const HUB_REPO = "thehub-pr";

const statusTone = {
  ok: "text-emerald-700 dark:text-emerald-300",
  failed: "text-red-700 dark:text-red-300",
  skipped: "text-slate-600 dark:text-slate-300",
};

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch (_error) {
    return value;
  }
}

export default function PipelineItemDetail() {
  const { itemId } = useParams();
  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    async function load() {
      const data = await getItem(decodeURIComponent(itemId || ""));
      if (!active) return;
      setItem(data);
      setLoading(false);
    }
    load();
    return () => {
      active = false;
    };
  }, [itemId]);

  if (loading) {
    return <div className="max-w-4xl mx-auto px-4 py-8 text-muted-foreground">Loading item…</div>;
  }

  if (!item) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8 space-y-4">
        <Link to="/pipeline" className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline">
          <ArrowLeft className="h-4 w-4" /> Back to pipeline
        </Link>
        <p className="rounded-xl border p-6 text-muted-foreground">
          Item not found. It may not have been classified yet, or the backend is not running.
        </p>
      </div>
    );
  }

  const pct = Math.round((Number(item.confidence) || 0) * 100);
  const dispatch = item.dispatch;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <Link to="/pipeline" className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline">
        <ArrowLeft className="h-4 w-4" /> Back to pipeline
      </Link>

      <div>
        <h1 className="text-2xl font-bold text-foreground">{item.title || "(untitled)"}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {item.source_name}
          {item.source_url ? (
            <a href={item.source_url} target="_blank" rel="noreferrer" className="ml-2 inline-flex items-center gap-1 text-primary hover:underline">
              source <ExternalLink className="h-3 w-3" />
            </a>
          ) : null}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {(item.labels || []).map((label) => (
          <DomainBadge key={label} domain={label} />
        ))}
        <ConfidenceBadge score={pct} />
        <EvidenceTierBadge tier={item.evidence_tier} />
      </div>

      {item.classifier_reasoning ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Classifier reasoning</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">{item.classifier_reasoning}</CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dispatch record</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          {!dispatch ? (
            <p className="text-muted-foreground">Not yet dispatched.</p>
          ) : (
            <div className="space-y-3">
              <p>
                Status: <span className={`font-semibold ${statusTone[dispatch.status] || ""}`}>{dispatch.status}</span>
                <span className="ml-3 text-muted-foreground">at {formatDate(dispatch.dispatched_at)}</span>
              </p>
              {dispatch.error ? <p className="text-red-700">Error: {dispatch.error}</p> : null}
              <ul className="divide-y rounded-lg border">
                {(dispatch.dispatched_to || []).map((repo) => (
                  <li key={repo} className="flex items-center justify-between px-3 py-2">
                    <span className="font-mono text-xs">{repo}</span>
                    {repo === HUB_REPO ? (
                      <Badge variant="outline" className="border-primary/40 bg-primary/10 font-semibold text-primary">Hub — always logged</Badge>
                    ) : (
                      <Badge variant="outline">domain-routed</Badge>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Content</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="whitespace-pre-wrap text-muted-foreground">{item.body_text || "(no body captured)"}</p>
          <div className="grid grid-cols-2 gap-2 pt-2 text-xs text-muted-foreground">
            <span>item_id: <span className="font-mono">{item.item_id}</span></span>
            <span>published: {formatDate(item.published_at)}</span>
            <span>captured: {formatDate(item.captured_at)}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
