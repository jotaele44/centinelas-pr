import { authorizeCentinelasOperation } from "./centinelasOperationGuard";

describe("Centinelas protected execution boundary", () => {
  const actor = { authenticated: true, userId: "u1", role: "operator" as const };

  it("rejects anonymous execution", () => {
    const r = authorizeCentinelasOperation(
      { authenticated: false, userId: null, role: null },
      { operation: "RUN_PIPELINE", idempotencyKey: "k1", staleHead: false, revoked: false }
    );
    expect(r.status).toBe(401);
  });

  it("rejects stale-head execution", () => {
    const r = authorizeCentinelasOperation(actor, { operation: "RUN_PIPELINE", idempotencyKey: "k1", staleHead: true, revoked: false });
    expect(r.reason).toBe("STALE_HEAD");
  });

  it("rejects revoked authority", () => {
    const r = authorizeCentinelasOperation(actor, { operation: "HANDOFF", idempotencyKey: "k1", staleHead: false, revoked: true });
    expect(r.reason).toBe("AUTHORITY_REVOKED");
  });

  it("requires idempotency keys", () => {
    const r = authorizeCentinelasOperation(actor, { operation: "DELIVER", idempotencyKey: null, staleHead: false, revoked: false });
    expect(r.reason).toBe("IDEMPOTENCY_KEY_REQUIRED");
  });

  it("allows operator handoff and delivery", () => {
    expect(authorizeCentinelasOperation(actor, { operation: "HANDOFF", idempotencyKey: "k1", staleHead: false, revoked: false }).allowed).toBeTrue();
    expect(authorizeCentinelasOperation(actor, { operation: "DELIVER", idempotencyKey: "k2", staleHead: false, revoked: false }).allowed).toBeTrue();
  });

  it("requires admin for retract and dispatch", () => {
    expect(authorizeCentinelasOperation(actor, { operation: "RETRACT", idempotencyKey: "k1", staleHead: false, revoked: false }).reason).toBe("ADMIN_REQUIRED");
    expect(authorizeCentinelasOperation(actor, { operation: "DISPATCH", idempotencyKey: "k2", staleHead: false, revoked: false }).reason).toBe("ADMIN_REQUIRED");
  });
});
