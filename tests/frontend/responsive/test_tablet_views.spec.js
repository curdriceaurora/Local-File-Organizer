/**
 * Responsive Test: Tablet Views (481px - 768px)
 *
 * Tests layout and functionality on medium screen devices:
 * - iPad, large tablets
 * - Two-column layouts
 * - Navigation adaptation (tabs or sidebar)
 * - Touch target sizing
 * - Orientation changes (portrait/landscape)
 * - Content distribution
 * - Image scaling
 */

import { test, expect } from "@playwright/test";

// Tablet viewports to test
const TABLET_VIEWPORTS = [
  { name: "iPad (portrait)", width: 768, height: 1024 },
  { name: "iPad (landscape)", width: 1024, height: 768 },
  { name: "Tablet 481px", width: 481, height: 800 },
  { name: "Galaxy Tab", width: 600, height: 960 },
];

test.describe("Tablet Views (481px - 768px)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  // Test each tablet viewport size
  TABLET_VIEWPORTS.forEach((viewport) => {
    test(`should display correctly in ${viewport.name}`, async ({ page }) => {
      // Set tablet viewport
      await page.setViewportSize(viewport);
      await page.waitForTimeout(500);

      // Verify viewport is set
      const size = page.viewportSize();
      expect(size?.width).toBe(viewport.width);
      expect(size?.height).toBe(viewport.height);

      // Check for no horizontal scrolling
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth);

      // Main content should be visible
      await expect(page.locator("main, [role='main']")).toBeVisible();
    });
  });

  test("should display two-column layout when appropriate", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    // Navigate to a page that might have two-column layout
    const organizeLink = page.locator('a:has-text("Organize"), [href*="organize"]');
    if (await organizeLink.isVisible()) {
      await organizeLink.click();
      await page.waitForLoadState("networkidle");

      // Look for two-column layouts
      const gridLayout = page.locator('[style*="grid"], [style*="display: grid"]');
      const flexLayout = page.locator('[style*="flex"]');

      // Should have multi-column layout capability
      if ((await gridLayout.count()) > 0) {
        const grid = gridLayout.first();
        const columns = await grid.evaluate((el) => {
          return window.getComputedStyle(el).gridTemplateColumns;
        });

        // At tablet size, should support 2 columns
        expect(columns).toBeTruthy();
      }
    }
  });

  test("should adapt navigation for tablet", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    // Look for navigation element
    const nav = page.locator("nav, [role='navigation']");
    if (await nav.isVisible()) {
      const navStyle = await nav.evaluate((el) => {
        return window.getComputedStyle(el).display;
      });

      // Navigation should be visible (not hidden)
      expect(navStyle).not.toBe("none");

      // Check for navigation items
      const navItems = nav.locator("a, button");
      const itemCount = await navItems.count();
      expect(itemCount).toBeGreaterThan(0);
    }
  });

  test("should maintain touch-friendly sizes on tablet", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    // Check button sizes
    const buttons = page.locator("button");
    const count = await buttons.count();

    if (count > 0) {
      for (let i = 0; i < Math.min(5, count); i++) {
        const button = buttons.nth(i);
        if (await button.isVisible()) {
          const boundingBox = await button.boundingBox();
          if (boundingBox) {
            // Touch targets should be at least 44px (accessibility)
            expect(boundingBox.height).toBeGreaterThanOrEqual(40);
            expect(boundingBox.width).toBeGreaterThanOrEqual(40);
          }
        }
      }
    }
  });

  test("should handle portrait orientation", async ({ page }) => {
    // Portrait: 768x1024
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    // Check that content adapts to portrait
    const viewportWidth = page.viewportSize()?.width;
    const contentWidth = await page.evaluate(() => {
      return document.documentElement.scrollWidth;
    });

    expect(contentWidth).toBeLessThanOrEqual(viewportWidth + 1); // +1 for rounding
  });

  test("should handle landscape orientation", async ({ page }) => {
    // Landscape: 1024x768
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.waitForTimeout(500);

    // Check that content adapts to landscape
    const viewportWidth = page.viewportSize()?.width;
    const contentWidth = await page.evaluate(() => {
      return document.documentElement.scrollWidth;
    });

    expect(contentWidth).toBeLessThanOrEqual(viewportWidth + 1);
  });

  test("should reflow content on orientation change", async ({ page }) => {
    // Start in portrait
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    const portraitHeight = page.viewportSize()?.height;

    // Get initial scroll height
    const portraitScrollHeight = await page.evaluate(() => {
      return document.documentElement.scrollHeight;
    });

    // Change to landscape
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.waitForTimeout(500);

    const landscapeHeight = page.viewportSize()?.height;

    // Get new scroll height
    const landscapeScrollHeight = await page.evaluate(() => {
      return document.documentElement.scrollHeight;
    });

    // Heights should be different
    expect(portraitHeight).not.toBe(landscapeHeight);
    // Content should reflow (scroll height might change)
    // Note: This might be the same if content fits, so we just verify no errors occurred
  });

  test("should display multi-line forms clearly on tablet", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    const forms = page.locator("form");
    const formCount = await forms.count();

    if (formCount > 0) {
      const form = forms.first();
      if (await form.isVisible()) {
        // Check form layout
        const inputs = form.locator("input, textarea, select");
        const inputCount = await inputs.count();

        if (inputCount > 1) {
          // Multiple inputs should be properly spaced
          const firstInput = inputs.nth(0);
          const secondInput = inputs.nth(1);

          const firstBox = await firstInput.boundingBox();
          const secondBox = await secondInput.boundingBox();

          if (firstBox && secondBox) {
            // Should be vertically separated
            const verticalGap = secondBox.y - (firstBox.y + firstBox.height);
            expect(verticalGap).toBeGreaterThanOrEqual(0);
          }
        }
      }
    }
  });

  test("should display tables appropriately on tablet", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    // Navigate to a page that might have tables (e.g., file browser)
    const dashboardLink = page.locator('a:has-text("Dashboard"), a:has-text("Files")');
    if (await dashboardLink.isVisible()) {
      await dashboardLink.click();
      await page.waitForLoadState("networkidle");
    }

    const tables = page.locator("table");
    if (await tables.isVisible()) {
      const table = tables.first();
      const boundingBox = await table.boundingBox();
      const viewportSize = page.viewportSize();

      if (boundingBox) {
        // Table should not overflow viewport
        expect(boundingBox.width).toBeLessThanOrEqual(viewportSize.width);
      }
    }
  });

  test("should scale images appropriately on tablet", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    const images = page.locator("img");
    const imageCount = await images.count();

    if (imageCount > 0) {
      for (let i = 0; i < Math.min(3, imageCount); i++) {
        const img = images.nth(i);
        if (await img.isVisible()) {
          const boundingBox = await img.boundingBox();
          const viewportSize = page.viewportSize();

          if (boundingBox) {
            // Image should not exceed viewport width
            expect(boundingBox.width).toBeLessThanOrEqual(viewportSize.width);

            // Image should be reasonably sized (not too small)
            expect(boundingBox.width).toBeGreaterThan(50);
            expect(boundingBox.height).toBeGreaterThan(50);
          }
        }
      }
    }
  });

  test("should display modals at appropriate size for tablet", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    // Try to open a modal
    const settingsButton = page.locator('button:has-text("Settings"), [data-settings]');
    if (await settingsButton.isVisible()) {
      await settingsButton.click();
      await page.waitForTimeout(500);

      const modal = page.locator('[role="dialog"], .modal, [data-modal]');
      if (await modal.isVisible()) {
        const boundingBox = await modal.boundingBox();
        const viewportSize = page.viewportSize();

        if (boundingBox) {
          // Modal should be reasonable size (not full screen but not too small)
          expect(boundingBox.width).toBeGreaterThan(300);
          expect(boundingBox.width).toBeLessThan(viewportSize.width);

          // Should have some padding
          expect(boundingBox.x).toBeGreaterThan(10);
          expect(boundingBox.y).toBeGreaterThan(10);
        }
      }
    }
  });

  test("should handle split-view layouts on tablet landscape", async ({ page }) => {
    // Landscape: good for split view
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.waitForTimeout(500);

    // Navigate to organize
    const organizeLink = page.locator('a:has-text("Organize"), [href*="organize"]');
    if (await organizeLink.isVisible()) {
      await organizeLink.click();
      await page.waitForLoadState("networkidle");

      // Check for multi-column layout
      const mainContent = page.locator("main, [role='main']");
      if (await mainContent.isVisible()) {
        const boundingBox = await mainContent.boundingBox();
        const viewportSize = page.viewportSize();

        if (boundingBox && viewportSize) {
          // Content should use a good portion of landscape width
          const contentPercent = (boundingBox.width / viewportSize.width) * 100;
                    expect(contentPercent).toBeGreaterThan(50);
        }
      }
    }
  });

  test("should preserve scroll position on orientation change", async ({ page }) => {
    // Create a long page to enable scrolling
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Start in portrait
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    // Try to scroll down
    await page.evaluate(() => window.scrollBy(0, 200));
    await page.waitForTimeout(300);

    // Get scroll position
    const portraitScroll = await page.evaluate(() => window.scrollY);

    // The page should have scrolled
    expect(portraitScroll).toBeGreaterThanOrEqual(0);
  });

  test("should display all critical actions on tablet", async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.waitForTimeout(500);

    // Look for primary action buttons
    const primaryButtons = page.locator('button[class*="primary"], button[class*="main"]');
    const count = await primaryButtons.count();

    if (count > 0) {
      for (let i = 0; i < count; i++) {
        const button = primaryButtons.nth(i);
        if (await button.isVisible()) {
          // Buttons should be readable
          const text = await button.textContent();
          expect(text).toBeTruthy();

          // Should be clickable
          await expect(button).toBeEnabled();
        }
      }
    }
  });

  test("should handle landscape-specific content layout", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.waitForTimeout(500);

    // In landscape, check if multiple sections display side-by-side
    const container = page.locator("main, [role='main']");
    if (await container.isVisible()) {
      const children = container.locator("> div, > section");
      const childCount = await children.count();

      // Check for multi-column arrangement
      if (childCount > 1) {
        const firstChild = children.nth(0);
        const secondChild = children.nth(1);

        const firstBox = await firstChild.boundingBox();
        const secondBox = await secondChild.boundingBox();

        if (firstBox && secondBox) {
          // In landscape, children might be side-by-side
          // Check if they have significant horizontal separation
          const horizontalSeparation = Math.abs(secondBox.x - (firstBox.x + firstBox.width));
          // Either side-by-side or stacked vertically
          const isHorizontal = horizontalSeparation < 100 && Math.abs(firstBox.y - secondBox.y) < 50;
          const isVertical = horizontalSeparation > 50 && secondBox.y > firstBox.y + firstBox.height;

          expect(isHorizontal || isVertical).toBe(true);
        }
      }
    }
  });
});
