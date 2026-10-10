import { describe, expect, it } from "vitest";
import { decideHomeEntry } from "./homeEntryGuard";

describe("federation Home entry contract", () => {
  it("allows the canonical Home control", () => {
    expect(decideHomeEntry(true, true, false)).toBe("HOME_CONTROL");
  });

  it("allows one cold-start Home entry", () => {
    expect(decideHomeEntry(false, false, true)).toBe("COLD_START");
    expect(decideHomeEntry(false, true, true)).toBe("DENIED");
  });

  it("denies incidental Home entry during a non-home session", () => {
    expect(decideHomeEntry(false, false, false)).toBe("DENIED");
    expect(decideHomeEntry(false, true, false)).toBe("DENIED");
  });
});
