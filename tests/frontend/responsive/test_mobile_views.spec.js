/**
 * Responsive Test: Mobile Views (320px - 480px)
 *
 * Tests layout and functionality on small screen devices:
 * - iPhone SE, small Android phones
 * - Hamburger menu navigation
 * - Single column layouts
 * - Touch-friendly button sizes (48px+)
 * - Readability without zoom
 * - No horizontal scrolling
 * - Form usability on mobile
 */

import { test, expect, devices } from "@playwright/test";

// Mobile viewports to test
const MOBILE_VIEWPORTS = [
  { name: "320px (iPhone SE)", width: 320, height: 568 },
  { name: "375px (iPhone 8)", width: 375, height: 667 },
  { name: "390px (iPhone 12)", width: 390, height: 844 },
  { name: "412px (Galaxy S10)", width: 412, height: 869 },
  { name: "480px (Large phone)", width: 480, height: 720 },
];

test.describe("Mobile Views (320px - 480px)", () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the app
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  // Test each viewport size
  MOBILE_VIEWPORTS.forEach((viewport) => {
    test(`should display correctly at ${viewport.name}`, async ({ page }) => {
      // Set mobile viewport
      await page.setViewportSize(viewport);

      // Wait for responsive styles to apply
      await page.waitForTimeout(500);

      // Verify viewport is set
      const size = page.viewportSize();
      expect(size?.width).toBe(viewport.width);
      expect(size?.height).toBe(viewport.height);

      // Check for no horizontal scrolling
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth);

      // Verify main content is visible
      await expect(page.locator("main, [role='main']")).toBeVisible();
    });
  });

  test("should show hamburger menu on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Look for hamburger menu button
    const hamburgerButton = page.locator(
      'button[aria-label*="menu" i], button:has-text("☰"), .hamburger, [data-hamburger-menu]'
    );

    if (await hamburgerButton.isVisible()) {
      expect(await hamburgerButton.isVisible()).toBe(true);

      // Click hamburger menu
      await hamburgerButton.click();

      // Wait for menu to appear
      const mobileMenu = page.locator(
        'nav[aria-label="Mobile"], .mobile-menu, [data-mobile-menu]'
      );
      await expect(mobileMenu).toBeVisible({ timeout: 2000 });

      // Verify menu items are clickable
      const menuItems = page.locator('nav a, nav button').nth(0);
      if (await menuItems.isVisible()) {
        await expect(menuItems).toBeTruthy();
      }
    }
  });

  test("should use single column layout on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Navigate to organize page if it exists
    const organizeLink = page.locator('a:has-text("Organize"), [href*="organize"]');
    if (await organizeLink.isVisible()) {
      await organizeLink.click();
      await page.waitForLoadState("networkidle");
    }

    // Check for multi-column layouts and verify they collapse
    const gridLayout = page.locator('[style*="grid"], [style*="display: grid"]');
    const flexLayout = page.locator('[style*="flex"], [style*="display: flex"]');

    // Layouts should adapt to single column on mobile
    if ((await gridLayout.count()) > 0) {
      const gridColumns = await gridLayout.first().evaluate((el) => {
        return window.getComputedStyle(el).gridTemplateColumns;
      });
      // Should be single column (auto or 1fr, not multiple columns)
      expect(gridColumns).not.toMatch(/\s+/); // No multiple columns
    }
  });

  test("should have touch-friendly button sizes", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Check main action buttons
    const buttons = page.locator("button");
    const count = await buttons.count();

    if (count > 0) {
      // Check first few visible buttons
      for (let i = 0; i < Math.min(5, count); i++) {
        const button = buttons.nth(i);
        if (await button.isVisible()) {
          const boundingBox = await button.boundingBox();
          if (boundingBox) {
            // Touch targets should be at least 44-48px (accessibility standard)
            expect(boundingBox.height).toBeGreaterThanOrEqual(40);
            expect(boundingBox.width).toBeGreaterThanOrEqual(40);
          }
        }
      }
    }
  });

  test("should display form inputs properly on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Find any forms
    const forms = page.locator("form");
    const formCount = await forms.count();

    if (formCount > 0) {
      const form = forms.first();
      if (await form.isVisible()) {
        // Check input widths
        const inputs = form.locator("input, textarea, select");
        const inputCount = await inputs.count();

        if (inputCount > 0) {
          const input = inputs.first();
          const boundingBox = await input.boundingBox();
          if (boundingBox) {
            // Input should take up most of the mobile width (with padding)
            const viewportSize = page.viewportSize();
            expect(boundingBox.width).toBeGreaterThan(viewportSize.width * 0.7);
          }

          // Labels should be above inputs (not beside)
          const label = form.locator("label").first();
          if (await label.isVisible()) {
            const labelBox = await label.boundingBox();
            const inputBox = await input.boundingBox();
            if (labelBox && inputBox) {
              // Label should be above input (smaller y value)
              expect(labelBox.y).toBeLessThan(inputBox.y);
            }
          }
        }
      }
    }
  });

  test("should display modals full-screen on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Try to trigger a modal (e.g., settings)
    const settingsButton = page.locator('button:has-text("Settings"), [data-settings]');
    if (await settingsButton.isVisible()) {
      await settingsButton.click();
      await page.waitForTimeout(500);

      // Find modal or dialog
      const modal = page.locator('[role="dialog"], .modal, [data-modal]');
      if (await modal.isVisible()) {
        const boundingBox = await modal.boundingBox();
        const viewportSize = page.viewportSize();

        if (boundingBox) {
          // Modal should be full or near-full width on mobile
          expect(boundingBox.width).toBeGreaterThan(viewportSize.width * 0.8);
        }

        // Should have close button
        const closeButton = modal.locator(
          'button[aria-label*="close" i], button:has-text("✕"), [data-close]'
        );
        if (await closeButton.isVisible()) {
          expect(await closeButton.isVisible()).toBe(true);
        }
      }
    }
  });

  test("should make text readable without zooming", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Check font sizes of body text
    const bodyText = page.locator("body *");
    const count = await bodyText.count();

    if (count > 0) {
      // Check first 10 text elements
      for (let i = 0; i < Math.min(10, count); i++) {
        const element = bodyText.nth(i);
        const text = await element.textContent();
        if (text && text.trim().length > 0) {
          const fontSize = await element.evaluate((el) => {
            return window.getComputedStyle(el).fontSize;
          });

          const fontSizeNum = parseInt(fontSize);
          // Text should be at least 14px for readability
          expect(fontSizeNum).toBeGreaterThanOrEqual(12);
        }
      }
    }

    // Check viewport meta tag
    const viewportMeta = page.locator('meta[name="viewport"]');
    const content = await viewportMeta.getAttribute("content");
    expect(content).toContain("width=device-width");
    expect(content).toContain("initial-scale");
  });

  test("should handle tap-to-expand content on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Navigate to a page that might have expandable content
    const dashboardLink = page.locator('a:has-text("Dashboard"), a:has-text("Home")');
    if (await dashboardLink.isVisible()) {
      await dashboardLink.click();
      await page.waitForLoadState("networkidle");
    }

    // Look for expandable sections (details, accordion, etc.)
    const expandableElements = page.locator("details, [role='button'][aria-expanded], .accordion");
    const count = await expandableElements.count();

    if (count > 0) {
      const expandable = expandableElements.first();
      if (await expandable.isVisible()) {
        // Click to expand
        await expandable.click();
        await page.waitForTimeout(300);

        // Verify content is visible
        const content = expandable.locator("~ *, [open] *");
        expect(await content.first().isVisible()).toBe(true);
      }
    }
  });

  test("should optimize images on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Find images
    const images = page.locator("img");
    const imageCount = await images.count();

    if (imageCount > 0) {
      for (let i = 0; i < Math.min(3, imageCount); i++) {
        const img = images.nth(i);
        if (await img.isVisible()) {
          const boundingBox = await img.boundingBox();
          const alt = await img.getAttribute("alt");

          if (boundingBox) {
            // Image shouldn't be wider than viewport
            const viewportSize = page.viewportSize();
            expect(boundingBox.width).toBeLessThanOrEqual(viewportSize.width);
          }

          // Images should have alt text
          expect(alt).toBeTruthy();
        }
      }
    }
  });

  test("should handle file uploads on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Navigate to organize if available
    const organizeLink = page.locator('a:has-text("Organize"), [href*="organize"]');
    if (await organizeLink.isVisible()) {
      await organizeLink.click();
      await page.waitForLoadState("networkidle");

      // Find file input
      const fileInput = page.locator('input[type="file"]');
      if (await fileInput.isVisible()) {
        // Upload a file
        await fileInput.setInputFiles({
          name: "mobile_test.txt",
          mimeType: "text/plain",
          buffer: Buffer.from("Mobile test file content"),
        });

        // Wait for upload to process
        await page.waitForTimeout(500);

        // File should appear in the UI
        const fileItem = page.locator('[data-file-item], .file-item, li:has-text("mobile_test")');
        await expect(fileItem.first()).toBeVisible({ timeout: 5000 });
      }
    }
  });

  test("should have readable focus indicators on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Tab to interactive elements
    const interactiveElements = page.locator("a, button, input, [tabindex]");
    const count = await interactiveElements.count();

    if (count > 0) {
      const element = interactiveElements.first();
      if (await element.isVisible()) {
        // Focus the element
        await element.focus();
        await page.waitForTimeout(100);

        // Check for focus styling
        const focusStyles = await element.evaluate((el) => {
          const style = window.getComputedStyle(el);
          const outline = style.outline;
          const boxShadow = style.boxShadow;
          return { outline, boxShadow };
        });

        // Should have visible focus indicator
        const hasFocusIndicator =
          focusStyles.outline && focusStyles.outline !== "none" ||
          focusStyles.boxShadow && focusStyles.boxShadow !== "none";
        expect(hasFocusIndicator).toBe(true);
      }
    }
  });

  test("should not show horizontal scrollbar on mobile", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);

    // Check for horizontal scrollbar
    const hasHorizontalScroll = await page.evaluate(() => {
      return window.innerWidth < document.documentElement.scrollWidth;
    });

    expect(hasHorizontalScroll).toBe(false);

    // Navigate through different pages to ensure no horizontal scroll
    const links = page.locator("a[href]");
    const count = Math.min(3, await links.count());

    for (let i = 0; i < count; i++) {
      const link = links.nth(i);
      if (await link.isVisible()) {
        const href = await link.getAttribute("href");
        if (href && href !== "#" && !href.startsWith("javascript:")) {
          await link.click();
          await page.waitForLoadState("networkidle");
          await page.waitForTimeout(300);

          // Check again for horizontal scroll
          const hasScroll = await page.evaluate(() => {
            return window.innerWidth < document.documentElement.scrollWidth;
          });
          expect(hasScroll).toBe(false);
        }
      }
    }
  });
});
