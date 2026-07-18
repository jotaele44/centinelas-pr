import { appClient } from "@/api/appClient";
import { slugify } from "@/lib/lifecycle";

/**
 * List one appClient entity.
 *
 * Unlike the per-page helpers this replaces, it SURFACES failures instead of
 * swallowing them: it returns `{ rows, error }` where `rows` is always an array
 * and `error` is an `Error` (or `null`). That lets a page distinguish "the data
 * layer failed" from "there are no rows" — previously both looked identical.
 */
export async function safeList(entityName, sort, limit = 200) {
  const entity = appClient.entities?.[entityName];
  if (!entity?.list) return { rows: [], error: null };
  try {
    return { rows: await entity.list(sort, limit), error: null };
  } catch (error) {
    return { rows: [], error };
  }
}

const EMPTY = Promise.resolve({ rows: [], error: null });

/**
 * Shared loader for the localStorage "lifecycle" pages (Monitor, Signals,
 * Matters, MatterDetail, Handoff). Fetches only the slices a caller asks for and
 * reports the first error encountered (`null` if all succeeded).
 *
 * Centralizes the `safeList` calls that were copy-pasted across six pages.
 */
export async function loadLifecycle({
  signals = false,
  matters = false,
  records = false,
  sources = false,
  handoffs = false,
} = {}) {
  const [signalRes, matterRes, recordRes, sourceRes, handoffRes] = await Promise.all([
    signals ? safeList("Signal", "-captured_at", 200) : EMPTY,
    matters ? safeList("Matter", "-first_seen_at", 200) : EMPTY,
    records ? safeList("OfficialRecord", "-effective_date", 200) : EMPTY,
    sources ? safeList("Source", "name", 300) : EMPTY,
    handoffs ? safeList("HandoffCandidate", "-created_date", 50) : EMPTY,
  ]);

  const error =
    [signalRes, matterRes, recordRes, sourceRes, handoffRes]
      .map((result) => result.error)
      .find(Boolean) || null;

  return {
    signals: signalRes.rows,
    matters: matterRes.rows,
    records: recordRes.rows,
    sources: sourceRes.rows,
    handoffs: handoffRes.rows,
    error,
  };
}

/**
 * Derive entity profiles from signal + matter data. `Entity`/`EntityMention`
 * exist as entities but are seeded empty; the real entity data lives as string
 * arrays on signals (`entities`, `agencies`) and matters (`people`,
 * `organizations`, `agencies`). This aggregates those mentions into a de-duped
 * list keyed by a slug, tracking a coarse `type` and the signals each appears in.
 *
 * Returns `[{ name, type, slug, mentionCount, signalIds }]` sorted by mentions.
 */
export function deriveEntities(signals = [], matters = []) {
  const bySlug = new Map();

  const add = (name, type, signalId) => {
    const clean = String(name || "").trim();
    if (!clean) return;
    const slug = slugify(clean);
    if (!slug) return;
    let entry = bySlug.get(slug);
    if (!entry) {
      entry = { name: clean, type, slug, mentionCount: 0, signalIds: new Set() };
      bySlug.set(slug, entry);
    }
    // "agency" is the strongest classification; keep it if any mention says so.
    if (type === "agency") entry.type = "agency";
    entry.mentionCount += 1;
    if (signalId) entry.signalIds.add(signalId);
  };

  for (const signal of signals) {
    const sid = signal.signal_id || signal.id;
    (signal.agencies || []).forEach((name) => add(name, "agency", sid));
    (signal.entities || []).forEach((name) => add(name, "entity", sid));
  }
  for (const matter of matters) {
    (matter.agencies || []).forEach((name) => add(name, "agency"));
    (matter.people || []).forEach((name) => add(name, "person"));
    (matter.organizations || []).forEach((name) => add(name, "organization"));
  }

  return Array.from(bySlug.values())
    .map((entry) => ({ ...entry, signalIds: Array.from(entry.signalIds) }))
    .sort((a, b) => b.mentionCount - a.mentionCount || a.name.localeCompare(b.name));
}
