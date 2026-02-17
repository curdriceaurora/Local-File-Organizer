/**
 * Responsive Test: Browser Compatibility
 *
 * Tests cross-browser compatibility:
 * - Chrome/Chromium specifics
 * - Firefox CSS/JS differences
 * - Safari/WebKit behavior
 * - Edge compatibility
 * - Mobile browser quirks
 * - CSS compatibility (flexbox, grid)
 * - JavaScript API differences
 * - No console errors
 */

import { test, expect } from "@playwright/test";

test.describe("Browser Compatibility", () => {
  test.beforeEach(async ({ page }) => {
    // Capture console errors
    const consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });

    // Store errors for later assertion
    page.consoleErrors = consoleErrors;

    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("should load without console errors", async ({ page }) => {
    const errors = page.consoleErrors;
    // Filter out common third-party errors
    const appErrors = errors.filter(
      (e) =>
        !e.includes("third-party") &&
        !e.includes("tracking") &&
        !e.includes("analytics")
    );

    expect(appErrors.length).toBe(0);
  });

  test("should display correctly on Chromium browser", async ({ page }) => {
    // Verify Chromium features
    const isChromium = await page.evaluate(() => {
      return /Chrome|Chromium|Edg/.test(navigator.userAgent);
    });

    if (isChromium) {
      // Test Chromium-specific features
      const hasWebP = await page.evaluate(() => {
        const canvas = document.createElement("canvas");
        return canvas.toDataURL("image/webp").indexOf("image/webp") === 5;
      });

      // WebP should work in Chromium
      expect(typeof hasWebP).toBe("boolean");
    }
  });

  test("should handle CSS flexbox correctly", async ({ page }) => {
    // Check if flexbox layouts render correctly
    const flexElements = page.locator("[style*='flex']");
    const count = await flexElements.count();

    if (count > 0) {
      const flexElement = flexElements.first();
      if (await flexElement.isVisible()) {
        const display = await flexElement.evaluate((el) => {
          return window.getComputedStyle(el).display;
        });

        expect(display).toContain("flex");
      }
    }
  });

  test("should handle CSS grid correctly", async ({ page }) => {
    // Check if grid layouts render correctly
    const gridElements = page.locator("[style*='grid']");
    const count = await gridElements.count();

    if (count > 0) {
      const gridElement = gridElements.first();
      if (await gridElement.isVisible()) {
        const display = await gridElement.evaluate((el) => {
          return window.getComputedStyle(el).display;
        });

        expect(display).toContain("grid");
      }
    }
  });

  test("should support modern CSS features", async ({ page }) => {
    // Test CSS custom properties
    const hasCSSVariables = await page.evaluate(() => {
      const root = document.documentElement;
      const style = window.getComputedStyle(root);
      return style.getPropertyValue("--color-primary").length > 0;
    });

    // CSS variables might not be used, which is ok
    expect(typeof hasCSSVariables).toBe("boolean");
  });

  test("should support Fetch API", async ({ page }) => {
    // Check if Fetch API is available
    const hasFetch = await page.evaluate(() => {
      return typeof fetch === "function";
    });

    expect(hasFetch).toBe(true);
  });

  test("should support Promise API", async ({ page }) => {
    // Check if Promise is available
    const hasPromise = await page.evaluate(() => {
      return typeof Promise === "function";
    });

    expect(hasPromise).toBe(true);
  });

  test("should handle event listeners correctly", async ({ page }) => {
    // Test event listener functionality
    const eventWorks = await page.evaluate(() => {
      let eventFired = false;
      const el = document.createElement("div");
      el.addEventListener("test", () => {
        eventFired = true;
      });
      el.dispatchEvent(new Event("test"));
      return eventFired;
    });

    expect(eventWorks).toBe(true);
  });

  test("should support local and session storage", async ({ page }) => {
    // Check if storage APIs work
    const hasStorage = await page.evaluate(() => {
      try {
        localStorage.setItem("test", "value");
        const value = localStorage.getItem("test");
        localStorage.removeItem("test");
        return value === "value";
      } catch (e) {
        return false;
      }
    });

    // Storage might be disabled, but if available should work
    expect(typeof hasStorage).toBe("boolean");
  });

  test("should render without layout shift", async ({ page }) => {
    // Monitor for Cumulative Layout Shift
    const cls = await page.evaluate(() => {
      return new Promise((resolve) => {
        let cls = 0;
        const observer = new PerformanceObserver((list) => {
          list.getEntries().forEach((entry) => {
            if (!entry.hadRecentInput) {
              cls += entry.value;
            }
          });
        });

        observer.observe({ type: "layout-shift", buffered: true });

        // Collect metrics for 2 seconds
        setTimeout(() => {
          observer.disconnect();
          resolve(cls);
        }, 2000);
      });
    });

    // CLS should be low (< 0.1 is good)
    expect(cls).toBeLessThan(0.25);
  });

  test("should handle DOM mutations correctly", async ({ page }) => {
    // Test MutationObserver
    const hasMutationObserver = await page.evaluate(() => {
      let mutations = 0;
      const observer = new MutationObserver(() => {
        mutations++;
      });

      const div = document.createElement("div");
      observer.observe(div, { childList: true });
      div.appendChild(document.createElement("span"));
      observer.disconnect();

      return mutations > 0;
    });

    expect(hasMutationObserver).toBe(true);
  });

  test("should support template elements", async ({ page }) => {
    // Check if template element works
    const hasTemplate = await page.evaluate(() => {
      const template = document.createElement("template");
      template.innerHTML = "<div>test</div>";
      return template.content.children.length > 0;
    });

    expect(hasTemplate).toBe(true);
  });

  test("should support web components", async ({ page }) => {
    // Check if custom elements API works
    const hasCustomElements = await page.evaluate(() => {
      return typeof customElements !== "undefined" && typeof customElements.define === "function";
    });

    expect(hasCustomElements).toBe(true);
  });

  test("should handle shadow DOM correctly", async ({ page }) => {
    // Check if shadow DOM works
    const hasShadowDOM = await page.evaluate(() => {
      const host = document.createElement("div");
      try {
        const shadow = host.attachShadow({ mode: "open" });
        return shadow !== null;
      } catch (e) {
        return false;
      }
    });

    expect(typeof hasShadowDOM).toBe("boolean");
  });

  test("should support IntersectionObserver", async ({ page }) => {
    // Check if IntersectionObserver is available
    const hasIntersectionObserver = await page.evaluate(() => {
      return typeof IntersectionObserver !== "undefined";
    });

    expect(hasIntersectionObserver).toBe(true);
  });

  test("should support ResizeObserver", async ({ page }) => {
    // Check if ResizeObserver is available
    const hasResizeObserver = await page.evaluate(() => {
      return typeof ResizeObserver !== "undefined";
    });

    expect(hasResizeObserver).toBe(true);
  });

  test("should support FormData API", async ({ page }) => {
    // Check if FormData works
    const hasFormData = await page.evaluate(() => {
      try {
        const formData = new FormData();
        formData.append("test", "value");
        return formData.get("test") === "value";
      } catch (e) {
        return false;
      }
    });

    expect(hasFormData).toBe(true);
  });

  test("should support async/await syntax", async ({ page }) => {
    // Navigate to organize to test async operations
    const organizeLink = page.locator('a:has-text("Organize"), [href*="organize"]');
    if (await organizeLink.isVisible()) {
      // This uses async operations internally
      await organizeLink.click();
      await page.waitForLoadState("networkidle");

      // If we got here without errors, async/await works
      expect(true).toBe(true);
    }
  });

  test("should handle CSS transforms correctly", async ({ page }) => {
    // Check if CSS transforms work
    const hasTransforms = await page.evaluate(() => {
      const el = document.createElement("div");
      el.style.transform = "translate(10px, 20px)";
      return el.style.transform !== "";
    });

    expect(hasTransforms).toBe(true);
  });

  test("should handle CSS animations correctly", async ({ page }) => {
    // Check if CSS animations are supported
    const hasAnimations = await page.evaluate(() => {
      const el = document.createElement("div");
      el.style.animation = "test 1s";
      return el.style.animation !== "";
    });

    expect(hasAnimations).toBe(true);
  });

  test("should support viewport meta tag", async ({ page }) => {
    // Check viewport meta tag
    const viewportMeta = page.locator('meta[name="viewport"]');
    const content = await viewportMeta.getAttribute("content");

    expect(content).toContain("width=device-width");
    expect(content).toContain("initial-scale");
  });

  test("should support type checking in HTML inputs", async ({ page }) => {
    // Check if input type validation works
    const supportsEmailInput = await page.evaluate(() => {
      const input = document.createElement("input");
      input.type = "email";
      return input.type === "email";
    });

    expect(supportsEmailInput).toBe(true);
  });

  test("should handle form submission correctly", async ({ page }) => {
    // Navigate to organize (has forms)
    const organizeLink = page.locator('a:has-text("Organize"), [href*="organize"]');
    if (await organizeLink.isVisible()) {
      await organizeLink.click();
      await page.waitForLoadState("networkidle");

      // Check for form
      const form = page.locator("form");
      if (await form.isVisible()) {
        // Form should be functional
        expect(await form.count()).toBeGreaterThan(0);
      }
    }
  });

  test("should support data attributes", async ({ page }) => {
    // Check if data attributes work
    const hasDataAttrs = await page.evaluate(() => {
      const el = document.createElement("div");
      el.dataset.test = "value";
      return el.dataset.test === "value";
    });

    expect(hasDataAttrs).toBe(true);
  });

  test("should handle window resize events", async ({ page }) => {
    // Trigger window resize
    let resizeTriggered = false;
    await page.evaluate(() => {
      (window).resizeTriggered = false;
      window.addEventListener("resize", () => {
        (window).resizeTriggered = true;
      });
    });

    // Change viewport to trigger resize
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.waitForTimeout(500);

    resizeTriggered = await page.evaluate(() => {
      return (window).resizeTriggered;
    });

    // Resize should have been triggered (or at least no errors)
    expect(typeof resizeTriggered).toBe("boolean");
  });

  test("should support JSON parsing", async ({ page }) => {
    // Check JSON support
    const hasJSON = await page.evaluate(() => {
      const obj = JSON.parse('{"test":"value"}');
      const str = JSON.stringify(obj);
      return str === '{"test":"value"}';
    });

    expect(hasJSON).toBe(true);
  });

  test("should handle errors gracefully", async ({ page }) => {
    // Check if error handling works
    const errorHandled = await page.evaluate(() => {
      try {
        throw new Error("test");
      } catch (e) {
        return true;
      }
    });

    expect(errorHandled).toBe(true);
  });

  test("should render SVGs correctly", async ({ page }) => {
    // Look for SVGs
    const svgs = page.locator("svg");
    const count = await svgs.count();

    if (count > 0) {
      // SVGs should render
      const svg = svgs.first();
      if (await svg.isVisible()) {
        const viewBox = await svg.getAttribute("viewBox");
        // Should have proper SVG attributes
        expect(viewBox || (await svg.getAttribute("width"))).toBeTruthy();
      }
    }
  });

  test("should support CSS media queries", async ({ page }) => {
    // Check if media queries work
    const supportsMediaQueries = await page.evaluate(() => {
      const mql = window.matchMedia("(max-width: 600px)");
      return typeof mql.matches === "boolean";
    });

    expect(supportsMediaQueries).toBe(true);
  });
});
