export type CentinelasOperation = "RUN_PIPELINE" | "HANDOFF" | "DELIVER" | "RETRACT" | "DISPATCH";
export interface CentinelasActor {
  authenticated: boolean;
  userId: string | null;
  role: "viewer" | "operator" | "admin" | null;
}
export interface OperationRequest {
  operation: CentinelasOperation;
  idempotencyKey: string | null;
  staleHead: boolean;
  revoked: boolean;
}

export function authorizeCentinelasOperation(actor: CentinelasActor, req: OperationRequest) {
  if (!actor.authenticated || !actor.userId) return { allowed: false, status: 401, reason: "AUTH_REQUIRED" };
  if (req.revoked) return { allowed: false, status: 403, reason: "AUTHORITY_REVOKED" };
  if (req.staleHead) return { allowed: false, status: 409, reason: "STALE_HEAD" };
  if (!req.idempotencyKey) return { allowed: false, status: 409, reason: "IDEMPOTENCY_KEY_REQUIRED" };
  if (actor.role !== "operator" && actor.role !== "admin") return { allowed: false, status: 403, reason: "OPERATOR_REQUIRED" };
  if ((req.operation === "RETRACT" || req.operation === "DISPATCH") && actor.role !== "admin") {
    return { allowed: false, status: 403, reason: "ADMIN_REQUIRED" };
  }
  return { allowed: true, status: 200, reason: "AUTHORIZED" };
}
