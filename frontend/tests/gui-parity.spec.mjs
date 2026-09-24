import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

function findRepositoryRoot(start) {
  let current = start;
  while (current !== path.dirname(current)) {
    if (fs.existsSync(path.join(current, ".federation", "gui-capabilities.json"))) {
      return current;
    }
    current = path.dirname(current);
  }
  throw new Error("Could not locate .federation/gui-capabilities.json");
}

const here = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = findRepositoryRoot(here);
const manifest = JSON.parse(
  fs.readFileSync(
    path.join(repositoryRoot, ".federation", "gui-capabilities.json"),
    "utf8",
  ),
);

const routes = [
  ...new Set(
    manifest.capabilities
      .filter(
        (capability) =>
          capability.status === "active" && capability.classification !== "internal",
      )
      .flatMap((capability) => capability.frontend?.e2e_routes ?? []),
  ),
].sort();

test("manifest exposes at least one active GUI route", () => {
  expect(routes.length).toBeGreaterThan(0);
});

for (const route of routes) {
  test(`GUI route ${route} is rendered and discoverable`, async ({ page }) => {
    const runtimeFailures = [];
    page.on("pageerror", (error) => {
      runtimeFailures.push(`page error: ${error.message}`);
    });
    page.on("response", (response) => {
      if (response.status() >= 500) {
        runtimeFailures.push(`${response.status()} ${response.url()}`);
      }
    });

    if (route !== "/") {
      await page.goto("/", { waitUntil: "domcontentloaded" });
      const link = page.locator(`a[href="${route}"]`).first();
      await expect(
        link,
        `No clickable GUI navigation reaches ${route}`,
      ).toBeVisible();
      await link.click();
      await expect(page).toHaveURL(new RegExp(`${route.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/?$`));
    } else {
      await page.goto(route, { waitUntil: "domcontentloaded" });
    }

    await expect(page.locator("#root")).toBeVisible();
    await page.waitForTimeout(750);
    await expect(page.locator("body")).not.toContainText(
      /(?:something broke while rendering|page\s+not\s+found|route\s+not\s+found|404\s*—?\s*not\s+found)/i,
    );
    expect(runtimeFailures, runtimeFailures.join("\n")).toEqual([]);
  });
}

test("water disruption console is reachable through the app route", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const navigationLink = page.locator('a[href="/water-disruption"]').first();
  await expect(navigationLink).toHaveAccessibleName(
    /Interrupciones de agua|Water disruptions/,
  );
  await navigationLink.click();

  await expect(page).toHaveURL(/\/water-disruption\/?$/);
  await expect(
    page.getByRole("heading", { name: "Water Disruption Shadow Queue" }),
  ).toBeVisible();

  const consoleFrame = page.frameLocator(
    'iframe[title="Water disruption shadow console"]',
  );
  await expect(
    consoleFrame.getByRole("heading", { name: "Water Disruption Shadow Queue" }),
  ).toBeVisible();
  await expect(consoleFrame.getByText("Shadow mode")).toBeVisible();
});

test("home program timeline filter, sort, and search controls work", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/", { waitUntil: "domcontentloaded" });
  const timeline = page.getByRole("region", { name: "Program timeline and upcoming work" });
  await expect(timeline).toBeVisible();

  const all = timeline.getByRole("button", { name: "ALL", exact: true });
  const blocked = timeline.getByRole("button", { name: "BLOCKED", exact: true });
  await expect(all).toHaveClass(/bg-primary\/10/);
  await blocked.click();
  await expect(blocked).toHaveClass(/bg-primary\/10/);
  await expect(all).not.toHaveClass(/bg-primary\/10/);
  await all.click();
  await expect(all).toHaveClass(/bg-primary\/10/);

  const sort = timeline.getByRole("button", { name: /Priority|Name/ });
  await expect(sort).toHaveText(/Priority/);
  await sort.click();
  await expect(sort).toHaveText(/Name/);

  const search = timeline.getByPlaceholder("Search activity, function, or state");
  const empty = timeline.getByText("No timeline items match this filter.");
  await expect(empty).toBeHidden();
  await search.fill("zzz-no-such-timeline-item-zzz");
  await expect(empty).toBeVisible();
  await search.fill("");
  await expect(empty).toBeHidden();

  expect(pageErrors).toEqual([]);
});
