import { appClient } from "@/api/appClient";
import { mapLegacyLawToMatter, mapLegacyLawToSignal } from "@/lib/lifecycle";

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
 * Matters, MatterDetail, Handoff). Fetches only the slices a caller asks for,
 * fetches the legacy `Law` entity a single time when a Signal/Matter fallback
 * may be needed, and reports the first error encountered (`null` if all
 * succeeded).
 *
 * Centralizes the `safeList` + legacy-`Law` fallback that was copy-pasted
 * across six pages.
 */
export async function loadLifecycle({
  signals = false,
  matters = false,
  records = false,
  sources = false,
  handoffs = false,
} = {}) {
  const needLaw = signals || matters;
  const [signalRes, matterRes, recordRes, sourceRes, handoffRes, lawRes] = await Promise.all([
    signals ? safeList("Signal", "-captured_at", 200) : EMPTY,
    matters ? safeList("Matter", "-first_seen_at", 200) : EMPTY,
    records ? safeList("OfficialRecord", "-effective_date", 200) : EMPTY,
    sources ? safeList("Source", "name", 300) : EMPTY,
    handoffs ? safeList("HandoffCandidate", "-created_date", 50) : EMPTY,
    needLaw ? safeList("Law", "-last_action_date", 100) : EMPTY,
  ]);

  const legacyLaws = lawRes.rows;
  const error =
    [signalRes, matterRes, recordRes, sourceRes, handoffRes, lawRes]
      .map((result) => result.error)
      .find(Boolean) || null;

  return {
    signals: signals ? (signalRes.rows.length > 0 ? signalRes.rows : legacyLaws.map(mapLegacyLawToSignal)) : [],
    matters: matters ? (matterRes.rows.length > 0 ? matterRes.rows : legacyLaws.map(mapLegacyLawToMatter)) : [],
    records: recordRes.rows,
    sources: sourceRes.rows,
    handoffs: handoffRes.rows,
    error,
  };
}
