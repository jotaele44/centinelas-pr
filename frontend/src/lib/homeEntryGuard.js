import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const HOME_PERMIT_KEY = "prii:federation-home-permit:v1";
const COLD_HOME_CONSUMED_KEY = "prii:federation-cold-home-consumed:v1";
let memoryPermit = false;
let memoryColdConsumed = false;

function storage() {
  try { return typeof window === "undefined" ? null : window.sessionStorage; } catch { return null; }
}

function initialNavigationWasHome() {
  if (typeof window === "undefined") return false;
  try {
    const [entry] = performance.getEntriesByType("navigation");
    const initial = new URL(entry?.name || window.location.href, window.location.href);
    return initial.pathname === "/";
  } catch {
    return window.location.pathname === "/" && window.history.length <= 1;
  }
}

export function decideHomeEntry(explicitPermit, coldConsumed, initialNavigationHome) {
  if (explicitPermit) return "HOME_CONTROL";
  if (!coldConsumed && initialNavigationHome) return "COLD_START";
  return "DENIED";
}

export function permitHomeEntry() {
  memoryPermit = true;
  try { storage()?.setItem(HOME_PERMIT_KEY, "1"); } catch {}
}

export function consumeHomeEntryPermission() {
  const store = storage();
  let permitted = memoryPermit;
  let coldConsumed = memoryColdConsumed;
  try {
    permitted = permitted || store?.getItem(HOME_PERMIT_KEY) === "1";
    coldConsumed = coldConsumed || store?.getItem(COLD_HOME_CONSUMED_KEY) === "1";
  } catch {}
  const decision = decideHomeEntry(permitted, coldConsumed, initialNavigationWasHome());
  if (decision === "HOME_CONTROL") {
    memoryPermit = false;
    try { store?.removeItem(HOME_PERMIT_KEY); } catch {}
  } else if (decision === "COLD_START") {
    memoryColdConsumed = true;
    try { store?.setItem(COLD_HOME_CONSUMED_KEY, "1"); } catch {}
  }
  return decision;
}

export function useHomeEntryGate(fallback = "/dashboard") {
  const navigate = useNavigate();
  const [allowed, setAllowed] = useState(false);
  useEffect(() => {
    const decision = consumeHomeEntryPermission();
    if (decision === "DENIED") {
      navigate(fallback, { replace: true });
      return;
    }
    setAllowed(true);
  }, [fallback, navigate]);
  return allowed;
}
