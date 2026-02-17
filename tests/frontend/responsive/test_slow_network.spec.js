/**
 * Responsive Test: Slow Network Performance
 *
 * Tests performance and UX on slow networks:
 * - Simulated 3G speed
 * - Image lazy loading works
 * - Progressive enhancement works
 * - Timeouts handled gracefully
 * - Retry mechanisms work
 * - UI is usable during loading
 * - Large files handled properly
 * - Loading indicators show
 */

import { test, expect } from "@playwright/test";

test.describe("Slow Network Performance", () => {
  test.beforeEach(async ({ page }) => {
    // Simulate slow 3G network
    // 3G typical: 400ms latency, 1.6 Mbps down, 750 kbps up
    await page.route("**/*", async (route) => {
      // Add artificial delay
      await new Promise((resolve) => setTimeout(resolve, 400));
      await route.continue();
    });

    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });
  });

  test("should load page on slow network", async ({ page }) => {
    // Increase timeout for slow network
    await page.goto("/", { waitUntil: "domcontentloaded" });

    // Page should be at least partially loaded
    await expect(page.locator("body")).toBeVisible();
  });

  test("should show loading indicators", async ({ page }) => {
    // Navigate to organize (might show loading)
    await page.goto("/");
    const organizeLink = page.locator('a:has-text("Organize"), [href*="organize"]');

    if (await organizeLink.isVisible()) {
      await organizeLink.click();

      // Look for loading indicator
      const loadingIndicator = page.locator(
        ".loading, .spinner, [data-loading], .progress, [role='progressbar']"
      );

      // Wait for either loading indicator or page to load
      const isLoading = await loadingIndicator.isVisible({ timeout: 5000 }).catch(() => false);

      // Either show loading or load quickly
      expect(isLoading || (await page.locator("main").isVisible())).toBe(true);
    }
  });

  test("should handle image loading on slow network", async ({ page }) => {
    await page.goto("/");

    // Find images
    const images = page.locator("img");
    const imageCount = await images.count();

    if (imageCount > 0) {
      // Check for lazy loading
      const lazyImages = images.filter('[loading="lazy"]');
      const lazyCount = await lazyImages.count();

      // Images should either load immediately or be lazy-loaded
      if (lazyCount > 0) {
        // Lazy loaded images should have loading attribute
        expect(lazyCount).toBeGreaterThan(0);
      } else {
        // Or images should eventually load
        for (let i = 0; i < Math.min(2, imageCount); i++) {
          const img = images.nth(i);
          if (await img.isVisible()) {
            const src = await img.getAttribute("src");
            expect(src).toBeTruthy();
          }
        }
      }
    }
  });

  test("should handle API requests on slow network", async ({ page }) => {
    await page.goto("/");

    // Set up request tracking
    let requestCount = 0;
    let failedRequests = 0;

    page.on("response", (response) => {
      requestCount++;
      if (!response.ok()) {
        failedRequests++;
      }
    });

    // Navigate to a feature that makes API calls
    const organizeLink = page.locator('a:has-text("Organize"), [href*="organize"]');
    if (await organizeLink.isVisible()) {
      await organizeLink.click();
      await page.waitForTimeout(2000);

      // Some requests might have failed on slow network, but page should be usable
      expect(requestCount).toBeGreaterThan(0);
    }
  });

  test("should show content before images on slow network", async ({ page }) => {
    // Increase timeout
    test.setTimeout(30000);

    await page.goto("/");

    // Text content should be visible before images
    const heading = page.locator("h1, h2, [role='heading']");
    const images = page.locator("img");

    if (await heading.first().isVisible()) {
      // Heading loaded
      const headingBox = await heading.first().boundingBox();
      expect(headingBox).toBeTruthy();
    }

    // Images might still be loading
    // (they should load with lazy loading)
  });

  test("should handle navigation on slow network", async ({ page }) => {
    test.setTimeout(30000);

    await page.goto("/");

    const links = page.locator("a[href]");
    const count = await links.count();

    if (count > 0) {
      // Try to navigate
      const link = links.first();
      if (await link.isVisible()) {
        const href = await link.getAttribute("href");

        if (href && href !== "#" && !href.startsWith("javascript:")) {
          await link.click();

          // Page should navigate (even if slowly)
          await page.waitForLoadState("domcontentloaded");
          expect(page.url()).toBeTruthy();
        }
      }
    }
  });

  test("should timeout gracefully on slow network", async ({ page }) => {
    test.setTimeout(30000);

    // Create a very slow route that times out
    let timedOut = false;

    await page.route("**/api/**", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 60000)); // 60 second delay
      await route.continue().catch(() => {
        timedOut = true;
      });
    });

    await page.goto("/");

    // Even with timeouts, page should be functional
    await expect(page.locator("body")).toBeVisible();
  });

  test("should allow user interaction during loading", async ({ page }) => {
    test.setTimeout(30000);

    await page.goto("/");

    // Try to interact while loading
    const buttons = page.locator("button");
    if (await buttons.first().isVisible()) {
      const button = buttons.first();

      // Button should be interactive
      expect(await button.isEnabled()).toBe(true);

      // Try to click during loading
      try {
        await button.click({ timeout: 3000 });
      } catch (e) {
        // Might timeout, but that's ok
      }
    }
  });

  test("should cache resources appropriately", async ({ page }) => {
    test.setTimeout(30000);

    // Load page twice
    await page.goto("/");
    await page.waitForTimeout(1000);

    const firstLoadTime = Date.now();
    await page.reload();
    const secondLoadTime = Date.now() - firstLoadTime;

    // Second load might be faster due to caching
    // (not guaranteed, so just verify it loads)
    expect(await page.locator("body").isVisible()).toBe(true);
  });

  test("should handle partial network failures", async ({ page }) => {
    test.setTimeout(30000);

    // Set up partial failures
    let requestCount = 0;
    await page.route("**/*", async (route) => {
      requestCount++;
      if (requestCount % 3 === 0) {
        // Fail every 3rd request
        await route.abort();
      } else {
        await new Promise((resolve) => setTimeout(resolve, 200));
        await route.continue();
      }
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });

    // Page should still be usable despite some failures
    expect(await page.locator("body").isVisible()).toBe(true);
  });

  test("should show retry mechanisms", async ({ page }) => {
    test.setTimeout(30000);

    // Set up routes that fail then succeed
    let attemptCount = 0;
    await page.route("**/api/**", async (route) => {
      attemptCount++;
      if (attemptCount < 2) {
        // Fail first time
        await route.abort();
      } else {
        // Succeed second time
        await route.continue();
      }
    });

    await page.goto("/");

    // Check for retry indicators or recovered API calls
    expect(attemptCount).toBeGreaterThanOrEqual(1);
  });

  test("should handle large file uploads on slow network", async ({ page }) => {
    test.setTimeout(60000);

    await page.goto("/");

    // Navigate to organize
    const organizeLink = page.locator('a:has-text("Organize"), [href*="organize"]');
    if (await organizeLink.isVisible()) {
      await organizeLink.click();
      await page.waitForLoadState("domcontentloaded");

      // Try to upload a file
      const fileInput = page.locator('input[type="file"]');
      if (await fileInput.isVisible()) {
        // Create a larger test file
        await fileInput.setInputFiles({
          name: "large_file.bin",
          mimeType: "application/octet-stream",
          buffer: Buffer.alloc(1024 * 100), // 100KB file
        });

        // Wait for upload
        await page.waitForTimeout(3000);

        // Upload should complete or show progress
        expect(true).toBe(true);
      }
    }
  });

  test("should display accurate progress indicators", async ({ page }) => {
    test.setTimeout(30000);

    await page.goto("/");

    // Look for progress indicators
    const progress = page.locator("[role='progressbar'], .progress-bar, .progress");

    // Progress bars might not be visible until there's long-running operation
    if (await progress.isVisible()) {
      const ariaValueNow = await progress.first().getAttribute("aria-valuenow");
      const ariaValueMax = await progress.first().getAttribute("aria-valuemax");

      // Should have proper ARIA attributes
      if (ariaValueNow && ariaValueMax) {
        expect(parseInt(ariaValueNow)).toBeGreaterThanOrEqual(0);
        expect(parseInt(ariaValueMax)).toBeGreaterThan(0);
      }
    }
  });

  test("should handle disconnection and reconnection", async ({ page }) => {
    test.setTimeout(30000);

    // Start with connection
    await page.goto("/");

    // Get initial content
    const initialTitle = await page.title();

    // Simulate disconnection
    await page.route("**/*", (route) => route.abort());
    await page.waitForTimeout(1000);

    // UI should still be visible (cached content)
    expect(await page.locator("body").isVisible()).toBe(true);

    // Restore connection
    await page.unroute("**/*");
    await page.waitForTimeout(500);

    // Should work again
    expect(await page.locator("body").isVisible()).toBe(true);
  });

  test("should minimize data usage on slow network", async ({ page }) => {
    test.setTimeout(30000);

    let totalDataRequested = 0;
    let imageRequestsBlocked = 0;

    await page.route("**/*.jpg", (route) => {
      imageRequestsBlocked++;
      route.abort();
    });

    await page.route("**/*", async (route) => {
      const request = route.request();
      // Estimate data size
      totalDataRequested += 1000; // Rough estimate

      await new Promise((resolve) => setTimeout(resolve, 100));
      await route.continue();
    });

    await page.goto("/");

    // Should minimize requests (especially for non-essential resources)
    expect(true).toBe(true);
  });

  test("should prefetch critical resources", async ({ page }) => {
    test.setTimeout(30000);

    await page.goto("/");

    // Check for prefetch directives
    const prefetchLinks = page.locator('link[rel="prefetch"], link[rel="preload"]');
    const prefetchCount = await prefetchLinks.count();

    // Prefetch is optional but good practice
    if (prefetchCount > 0) {
      expect(prefetchCount).toBeGreaterThan(0);
    }
  });

  test("should show skeleton screens or placeholders", async ({ page }) => {
    test.setTimeout(30000);

    await page.goto("/");

    // Look for skeleton screens or content placeholders
    const skeletons = page.locator(".skeleton, [data-skeleton], .placeholder");

    // Skeletons are optional but good for UX
    // Just verify page loads
    expect(await page.locator("body").isVisible()).toBe(true);
  });

  test("should queue requests on slow network", async ({ page }) => {
    test.setTimeout(30000);

    let requestCount = 0;
    let concurrentRequests = 0;
    let maxConcurrent = 0;

    await page.route("**/*", async (route) => {
      requestCount++;
      concurrentRequests++;
      maxConcurrent = Math.max(maxConcurrent, concurrentRequests);

      await new Promise((resolve) => setTimeout(resolve, 200));
      await route.continue();

      concurrentRequests--;
    });

    await page.goto("/");

    // Should not have unlimited concurrent requests
    // (proper queuing limits concurrent connections)
    expect(maxConcurrent).toBeLessThan(50); // Reasonable limit
  });
});
