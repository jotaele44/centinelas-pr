import fs from "node:fs";
import path from "node:path";

describe("Centinelas successor v2 responsive containment", () => {
  it("constrains the mobile sidebar grid item instead of allowing intrinsic nav width to expand the page", () => {
    const css = fs.readFileSync(path.resolve("components/AppShell.module.css"), "utf8");
    expect(css).toContain(".sidebar {");
    expect(css).toContain("min-width: 0;");
    expect(css).toContain("max-width: 100%;");
  });

  it("preserves intentional internal horizontal scrolling on the nav", () => {
    const css = fs.readFileSync(path.resolve("components/AppShell.module.css"), "utf8");
    expect(css).toContain("overflow-x: auto;");
    expect(css).toContain(".navItem");
    expect(css).toContain("flex: 0 0 auto;");
  });
});
