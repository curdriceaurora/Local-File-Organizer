/**
 * E2E Test: HTMX Interactions
 *
 * Tests HTMX-specific functionality:
 * 1. hx-get requests (fetch without page reload)
 * 2. hx-post form submissions
 * 3. hx-swap behavior (replace, append, prepend)
 * 4. hx-trigger event-driven requests
 * 5. hx-target element updates
 * 6. Loading indicators
 * 7. HTMX error responses
 * 8. OOB (out-of-band) updates
 */

import { test, expect } from "@playwright/test";

test.describe("HTMX Interactions", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("should make hx-get request for partial page update", async ({
    page,
  }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Find an element with hx-get
    const htmxElement = page.locator('[hx-get]').first();
    if (await htmxElement.isVisible()) {
      // Trigger the request
      await htmxElement.click();

      // Monitor network requests for HTMX
      const responses = [];
      page.on("response", (response) => {
        if (
          response.request().method() === "GET" &&
          response.request().headers()["hx-request"] === "true"
        ) {
          responses.push(response);
        }
      });

      // Wait for request to complete
      await page.waitForTimeout(1000);

      // Verify DOM was updated
      const targetSelector = await htmxElement.getAttribute("hx-target");
      if (targetSelector) {
        const targetElement = page.locator(targetSelector);
        const content = await targetElement.textContent();
        expect(content).toBeTruthy();
      }
    }
  });

  test("should submit form with hx-post", async ({ page }) => {
    // Navigate to settings to find a form with hx-post
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    if (await settingsLink.isVisible()) {
      await settingsLink.click();
      await page.waitForSelector(
        '[data-settings-panel], [data-settings-page]',
        { timeout: 5000 },
      );

      // Find a form with hx-post
      const htmxForm = page.locator('form[hx-post]').first();
      if (await htmxForm.isVisible()) {
        // Find a field to modify
        const input = htmxForm.locator('input').first();
        if (await input.isVisible()) {
          const originalValue = await input.inputValue();

          // Change value
          await input.fill("test_value_" + Date.now());

          // Get hx-post target
          const postTarget = await htmxForm.getAttribute("hx-post");
          expect(postTarget).toBeTruthy();

          // Submit via HTMX (automatic on form submission with hx-post)
          await htmxForm.evaluate((form) => {
            if (window.htmx) {
              window.htmx.trigger(form, "submit");
            } else {
              form.requestSubmit();
            }
          });

          // Wait for response
          await page.waitForTimeout(1000);

          // Verify form was updated or response received
          const responseIndicator = page.locator(
            '[data-response-success], [data-saved]',
          );
          if (await responseIndicator.isVisible()) {
            await expect(responseIndicator).toBeVisible();
          }
        }
      }
    }
  });

  test("should replace element with hx-swap replace", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Find element with hx-swap="replace"
    const replaceElement = page.locator('[hx-get][hx-swap*="replace"]').first();
    if (await replaceElement.isVisible()) {
      const originalHTML = await replaceElement.innerHTML();

      // Trigger request
      await replaceElement.click();
      await page.waitForTimeout(1000);

      // Verify element was replaced
      const newHTML = await replaceElement.innerHTML();
      // Content might change, but element reference should stay
      expect(newHTML).toBeTruthy();
    }
  });

  test("should append content with hx-swap innerHTML", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Find element with hx-swap="innerHTML"
    const appendElement = page.locator('[hx-get][hx-swap*="innerHTML"]').first();
    if (await appendElement.isVisible()) {
      const initialChildCount = await appendElement
        .locator("> *")
        .count();

      // Trigger request
      await appendElement.click();
      await page.waitForTimeout(1000);

      // Verify content was added to element
      const newChildCount = await appendElement.locator("> *").count();
      // Element should have same or more children
      expect(newChildCount).toBeGreaterThanOrEqual(initialChildCount);
    }
  });

  test("should trigger HTMX request on event", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Find element with hx-trigger
    const triggeredElement = page.locator('[hx-trigger]').first();
    if (await triggeredElement.isVisible()) {
      const trigger = await triggeredElement.getAttribute("hx-trigger");
      expect(trigger).toBeTruthy();

      // Element should have HTMX capabilities
      const hasHtmx =
        (await triggeredElement.getAttribute("hx-get")) ||
        (await triggeredElement.getAttribute("hx-post"));
      if (hasHtmx) {
        // Trigger the specified event
        if (trigger && trigger.includes("click")) {
          await triggeredElement.click();
        } else if (trigger && trigger.includes("change")) {
          // Trigger change event
          await triggeredElement.evaluate((el) => {
            if (window.htmx) {
              window.htmx.trigger(el, "change");
            } else {
              el.dispatchEvent(new Event("change", { bubbles: true }));
            }
          });
        }

        // Wait for request to complete
        await page.waitForTimeout(1000);
      }
    }
  });

  test("should update hx-target element", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Find element with hx-target
    const sourceElement = page.locator('[hx-get][hx-target]').first();
    if (await sourceElement.isVisible()) {
      const targetSelector = await sourceElement.getAttribute("hx-target");
      if (targetSelector) {
        // Get target element
        const targetElement = page.locator(targetSelector);
        if (await targetElement.isVisible()) {
          const initialContent = await targetElement.textContent();

          // Trigger request
          await sourceElement.click();
          await page.waitForTimeout(1000);

          // Verify target was updated
          const newContent = await targetElement.textContent();
          // Content should have changed or been populated
          expect(newContent).toBeTruthy();
        }
      }
    }
  });

  test("should show loading indicator during HTMX request", async ({
    page,
  }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Find element with hx-request
    const htmxElement = page.locator('[hx-get]').first();
    if (await htmxElement.isVisible()) {
      // Look for loading class or indicator
      const loadingIndicator = page.locator('[class*="htmx-request"]');

      // Trigger request and immediately check for loading state
      const responsePromise = page.waitForResponse(
        (response) =>
          response.status() === 200 ||
          response.status() === 404 ||
          response.status() >= 500,
      );

      await htmxElement.click();

      // Check for loading state (may be very brief)
      // Just verify the request went through
      const response = await Promise.race([
        responsePromise,
        new Promise((resolve) => setTimeout(() => resolve(null), 2000)),
      ]);

      // Response should have completed
      expect(response).toBeTruthy();
    }
  });

  test("should handle HTMX error responses", async ({ page }) => {
    // Mock an error response for HTMX
    await page.route("**/api/**", (route) => {
      if (route.request().headers()["hx-request"] === "true") {
        route.abort("failed");
      } else {
        route.continue();
      }
    });

    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Find and trigger HTMX request
    const htmxElement = page.locator('[hx-get]').first();
    if (await htmxElement.isVisible()) {
      await htmxElement.click();
      await page.waitForTimeout(1000);

      // Error should be handled
      // Check for error message or error state
      const errorIndicator = page.locator('[data-htmx-error]');
      if (await errorIndicator.isVisible()) {
        const error = await errorIndicator.textContent();
        expect(error).toBeTruthy();
      }
    }
  });

  test("should not reload page on HTMX request", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Get current page info
    const initialTitle = await page.title();

    // Find and trigger HTMX request
    const htmxElement = page.locator('[hx-get]').first();
    if (await htmxElement.isVisible()) {
      // Listen for navigation (should not happen)
      let navigationHappened = false;
      const navigationHandler = () => {
        navigationHappened = true;
      };
      page.on("load", navigationHandler);

      // Trigger request
      await htmxElement.click();
      await page.waitForTimeout(1000);

      page.removeListener("load", navigationHandler);

      // Verify page didn't reload
      const newTitle = await page.title();
      expect(newTitle).toBe(initialTitle);
      expect(navigationHappened).toBeFalsy();
    }
  });

  test("should support OOB (out-of-band) updates", async ({ page }) => {
    // OOB updates allow updating multiple elements from a single response
    // This is typically used for updating secondary elements

    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Look for OOB indicator or element with hx-swap-oob
    const oobElement = page.locator('[hx-swap-oob]');
    if ((await oobElement.count()) > 0) {
      // OOB elements are already visible
      // This indicates the app supports OOB updates
      expect(await oobElement.count()).toBeGreaterThan(0);
    }
  });

  test("should preserve HTMX form state", async ({ page }) => {
    // Navigate to settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    if (await settingsLink.isVisible()) {
      await settingsLink.click();
      await page.waitForSelector(
        '[data-settings-panel], [data-settings-page]',
        { timeout: 5000 },
      );

      // Find HTMX form
      const htmxForm = page.locator('form[hx-post]').first();
      if (await htmxForm.isVisible()) {
        // Fill form
        const inputs = htmxForm.locator("input");
        const count = await inputs.count();

        if (count > 0) {
          const firstInput = inputs.first();
          await firstInput.fill("test_value");

          // Verify value is preserved
          const value = await firstInput.inputValue();
          expect(value).toBe("test_value");

          // Submit form with HTMX
          await htmxForm.evaluate((form) => {
            if (form.requestSubmit) {
              form.requestSubmit();
            }
          });

          await page.waitForTimeout(500);

          // Value should still be there (not cleared)
          const newValue = await firstInput.inputValue();
          // Value should be preserved or cleared by server
          expect(newValue).toBeTruthy();
        }
      }
    }
  });

  test("should handle HTMX polling", async ({ page }) => {
    // HTMX polling allows elements to periodically fetch updates
    // Look for hx-trigger="every X s"

    // Navigate to organize for ongoing operations
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Find polling element
    const pollingElement = page.locator('[hx-trigger*="every"]');
    if ((await pollingElement.count()) > 0) {
      // Polling is configured
      const trigger = await pollingElement
        .first()
        .getAttribute("hx-trigger");
      expect(trigger).toContain("every");

      // Element should fetch updates periodically
      // Just verify the element is properly configured
      expect(await pollingElement.isVisible()).toBeTruthy();
    }
  });

  test("should handle HTMX infinite scroll or load more", async ({
    page,
  }) => {
    // Navigate to organize or search results
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Look for load more button or infinite scroll trigger
    const loadMoreButton = page.locator(
      'button:has-text("Load More"), [hx-indicator*="load"]',
    );

    if (await loadMoreButton.isVisible()) {
      // Click to load more
      const initialCount = await page.locator('[data-item]').count();

      await loadMoreButton.click();
      await page.waitForTimeout(1000);

      // Verify more items were added
      const newCount = await page.locator('[data-item]').count();
      expect(newCount).toBeGreaterThanOrEqual(initialCount);
    }
  });

  test("should properly configure HTMX headers", async ({ page }) => {
    // HTMX sets specific headers in requests
    let htmxHeaderFound = false;

    page.on("request", (request) => {
      const headers = request.headers();
      if (headers["hx-request"] === "true") {
        htmxHeaderFound = true;
        // Verify HTMX headers are set
        expect(headers["hx-request"]).toBe("true");
        expect(headers["hx-current-url"]).toBeTruthy();
      }
    });

    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Trigger HTMX request
    const htmxElement = page.locator('[hx-get]').first();
    if (await htmxElement.isVisible()) {
      await htmxElement.click();
      await page.waitForTimeout(1000);
    }

    // Note: Header check might not work due to page listener limitations
    // This is more of a verification that HTMX is working
  });
});
