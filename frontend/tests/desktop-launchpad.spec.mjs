// End-to-end test of Centinelas's Launch Pad, the screen the desktop app opens
// on before the backend starts.
//
// The page is the runtime's real render of desktop/config.py, and every call it
// makes goes to the runtime's real DesktopBridge, served by
// tests/support/launchpad_harness.py. Only the native window is replaced: a
// window.pywebview.api shim forwards each call over HTTP. After Launch, the
// session is applied the way the desktop launcher applies it and the real
// backend answers under /app, behind the runtime's Guest guard.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const GUEST_REFUSAL = /Guest sessions are read-only/;

async function openLaunchPad(page) {
  await page.addInitScript(() => {
    const call = async (method, args) => {
      const response = await fetch(`/bridge/${method}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(args),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || body.detail || response.statusText);
      return body;
    };
    // pywebview exposes the bridge methods as promise-returning functions.
    window.pywebview = { api: new Proxy({}, { get: (_, method) => (...args) => call(method, args) }) };
  });
  await page.goto("/");
  await page.evaluate(() => window.dispatchEvent(new Event("pywebviewready")));
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator("#rows .row")).toHaveCount(4);
}

async function launchedSession(request) {
  await expect
    .poll(async () => (await (await request.get("/session")).json()).launched)
    .toBe(true);
  return (await request.get("/session")).json();
}

test("shows Centinelas's own readiness, start pages and entry modes", async ({ page }) => {
  await openLaunchPad(page);
  await expect(page.locator("#summary")).toContainText("Centinelas watches public sources");
  for (const label of ["Workspace", "Classified signals", "Waiting in queue", "Routed and handed off"]) {
    await expect(page.locator("#rows")).toContainText(label);
  }
  const starts = await page.locator("#start option").evaluateAll((options) => options.map((o) => o.value));
  expect(starts).toEqual([
    "/", "/dashboard", "/monitor", "/signals", "/matters", "/entidades",
    "/sources", "/pipeline", "/water-disruption", "/handoff",
  ]);
  await expect(page.getByRole("radio", { name: /Guest/ })).toBeVisible();
  await expect(page.getByRole("radio", { name: /Operator/ })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
  ).toBe(false);
});

async function blockingViolations(page) {
  const axe = await new AxeBuilder({ page }).analyze();
  return axe.violations.filter(({ impact }) => impact === "critical" || impact === "serious");
}

test("has no serious accessibility violation with every option active", async ({ page }) => {
  await openLaunchPad(page);
  await page.getByRole("radio", { name: /Operator/ }).check();
  const blocking = await blockingViolations(page);
  expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([]);
});

test("in Guest, the only violation is the runtime's dimmed locked options", async ({ page }) => {
  // Known defect in the shared runtime, not in this repository: prii_desktop
  // dims an Operator-only option in Guest with `.option.locked { opacity: .55 }`,
  // which takes its help text to about 2.4:1. Anything else fails this test,
  // and so does this defect once the runtime fixes it and this test is not
  // tightened to match.
  await openLaunchPad(page);
  await page.getByRole("radio", { name: /Guest/ }).check();
  const blocking = await blockingViolations(page);
  expect(blocking.map(({ id }) => id)).toEqual(["color-contrast"]);
  const insideLockedOption = await Promise.all(
    blocking[0].nodes.map(({ target }) =>
      page.locator(target.join(" ")).evaluate((node) => Boolean(node.closest(".option.locked"))),
    ),
  );
  expect(insideLockedOption.length).toBeGreaterThan(0);
  expect(insideLockedOption.every(Boolean)).toBe(true);
});

test("Guest opens on the chosen page and the backend refuses writes", async ({ page, request }) => {
  await openLaunchPad(page);
  await page.getByRole("radio", { name: /Guest/ }).check();
  // Every Centinelas option is Operator-only.
  await expect(page.locator("#option-route_min_confidence")).toBeDisabled();
  await page.getByLabel("Starting page").selectOption("/signals");
  await page.getByRole("button", { name: "Launch", exact: true }).click();

  const session = await launchedSession(request);
  expect(session.mode).toBe("guest");
  expect(session.start_route).toBe("/signals");

  expect((await request.get("/app/health")).status()).toBe(200);
  const write = await request.post("/app/handoffs/not-a-real-item", { data: { targets: ["thehub-pr"] } });
  expect(write.status()).toBe(403);
  expect((await write.json()).detail).toMatch(GUEST_REFUSAL);
});

test("Operator options reach the backend and writes get through", async ({ page, request }) => {
  await openLaunchPad(page);
  await page.getByRole("radio", { name: /Operator/ }).check();
  await expect(page.locator("#option-route_min_confidence")).toBeEnabled();
  await page.locator("#option-route_min_confidence").selectOption("0.70");
  await page.getByLabel("Starting page").selectOption("/pipeline");
  await page.getByRole("button", { name: "Launch", exact: true }).click();

  await expect
    .poll(async () => (await (await request.get("/session")).json()).mode)
    .toBe("operator");
  const session = await launchedSession(request);
  expect(session.start_route).toBe("/pipeline");
  expect(session.env.CENTINELAS_ROUTE_MIN_CONFIDENCE).toBe("0.70");

  // Past the guard, the handler itself answers: the item does not exist.
  const write = await request.post("/app/handoffs/not-a-real-item", { data: { targets: ["thehub-pr"] } });
  expect(write.status()).toBe(404);
  expect((await write.json()).detail).not.toMatch(GUEST_REFUSAL);
});
