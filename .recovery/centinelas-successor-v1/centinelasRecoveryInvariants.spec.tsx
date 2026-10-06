import { HISTORICAL_DATABASE_STATE, validateFeedRun, validateRecoveredRuntime } from "./centinelasRecoveryInvariants";

describe("Centinelas recovered runtime invariants", () => {
  it("accepts the recovered 100/100/87 unique denominator", () => {
    const r = validateRecoveredRuntime({
      signals: 100, distinctSignals: 100,
      matters: 100, distinctMatters: 100,
      sources: 87, distinctSources: 87,
      syntheticSignals: 0,
      orphanSignalMatterJoins: 0,
      orphanSignalSourceJoins: 0,
    });
    expect(r.pass).toBeTrue();
  });

  it("rejects synthetic operational signal residue", () => {
    const r = validateRecoveredRuntime({
      signals: 100, distinctSignals: 100,
      matters: 100, distinctMatters: 100,
      sources: 87, distinctSources: 87,
      syntheticSignals: 1,
      orphanSignalMatterJoins: 0,
      orphanSignalSourceJoins: 0,
    });
    expect(r.reasons).toContain("SYNTHETIC_SIGNAL_RESIDUE");
  });

  it("rejects orphan signal-to-matter joins", () => {
    const r = validateRecoveredRuntime({
      signals: 100, distinctSignals: 100,
      matters: 100, distinctMatters: 100,
      sources: 87, distinctSources: 87,
      syntheticSignals: 0,
      orphanSignalMatterJoins: 1,
      orphanSignalSourceJoins: 0,
    });
    expect(r.pass).toBeFalse();
  });

  it("closes the recovered 60 = 54 + 1 + 5 feed arithmetic", () => {
    expect(validateFeedRun({ configured: 60, success: 54, empty: 1, externalFailure: 5 }).pass).toBeTrue();
  });

  it("rejects unexplained feed-count residue", () => {
    expect(validateFeedRun({ configured: 60, success: 54, empty: 1, externalFailure: 4 }).reasons).toContain("FEED_ARITHMETIC_MISMATCH");
  });

  it("preserves historical database rows as unavailable rather than zero", () => {
    expect(HISTORICAL_DATABASE_STATE).toBe("UNAVAILABLE_NO_DUMP");
  });
});
