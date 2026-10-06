export interface CentinelasRecoveredCounts {
  signals: number;
  distinctSignals: number;
  matters: number;
  distinctMatters: number;
  sources: number;
  distinctSources: number;
  syntheticSignals: number;
  orphanSignalMatterJoins: number;
  orphanSignalSourceJoins: number;
}

export interface FeedRunSummary {
  configured: number;
  success: number;
  empty: number;
  externalFailure: number;
}

export function validateRecoveredRuntime(c: CentinelasRecoveredCounts) {
  const reasons: string[] = [];
  if (c.signals !== c.distinctSignals) reasons.push("SIGNAL_DUPLICATES");
  if (c.matters !== c.distinctMatters) reasons.push("MATTER_DUPLICATES");
  if (c.sources !== c.distinctSources) reasons.push("SOURCE_DUPLICATES");
  if (c.syntheticSignals !== 0) reasons.push("SYNTHETIC_SIGNAL_RESIDUE");
  if (c.orphanSignalMatterJoins !== 0) reasons.push("ORPHAN_SIGNAL_MATTER");
  if (c.orphanSignalSourceJoins !== 0) reasons.push("ORPHAN_SIGNAL_SOURCE");
  return { pass: reasons.length === 0, reasons };
}

export function validateFeedRun(f: FeedRunSummary) {
  const reasons: string[] = [];
  if (f.configured !== f.success + f.empty + f.externalFailure) reasons.push("FEED_ARITHMETIC_MISMATCH");
  if ([f.configured, f.success, f.empty, f.externalFailure].some(v => v < 0)) reasons.push("NEGATIVE_COUNT");
  return { pass: reasons.length === 0, reasons };
}

export const HISTORICAL_DATABASE_STATE = "UNAVAILABLE_NO_DUMP" as const;
