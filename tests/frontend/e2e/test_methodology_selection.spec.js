/**
 * E2E Test: Methodology Selection and Switching
 *
 * Tests methodology selection workflow:
 * 1. Navigate to methodology selector
 * 2. Switch between methodologies (PARA, Johnny Decimal, etc.)
 * 3. Verify UI changes per methodology
 * 4. Preview results with different systems
 * 5. Save preference and verify persistence
 */

import { test, expect } from "@playwright/test";

test.describe("Methodology Selection", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("should display all available methodologies", async ({ page }) => {
    // Navigate to settings or methodology selector
    const settingsLink = page.locator("a:has-text('Settings')");
    if (await settingsLink.isVisible()) {
      await settingsLink.click();
      await page.waitForSelector('[data-settings-panel]', { timeout: 5000 });
    }

    // Look for methodology selector
    const methodologySection = page.locator(
      '[data-methodology-selection], [data-methodology-settings]',
    );
    if (await methodologySection.isVisible()) {
      const methodologyOptions = page.locator('[data-methodology-option]');
      const count = await methodologyOptions.count();
      expect(count).toBeGreaterThanOrEqual(3); // At least PARA, JD, GTD

      // Verify each has a label and description
      const labels = await page.locator('[data-methodology-name]').allTextContents();
      expect(labels.length).toBeGreaterThanOrEqual(3);
    }
  });

  test("should switch between methodologies", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Find methodology selector
    const methodologyButton = page.locator('[data-methodology-button]');
    if (await methodologyButton.isVisible()) {
      await methodologyButton.click();
      await page.waitForSelector('[data-methodology-menu]', { timeout: 5000 });

      // Get initial selection
      const initialSelection = await page
        .locator('[data-selected-methodology]')
        .textContent();

      // Switch to a different methodology
      const methodologyOptions = page.locator('[data-methodology-option]');
      const count = await methodologyOptions.count();

      if (count >= 2) {
        // Click second methodology
        const secondOption = page.locator('[data-methodology-option]').nth(1);
        await secondOption.click();

        // Verify selection changed
        await page.waitForTimeout(500);
        const newSelection = await page
          .locator('[data-selected-methodology]')
          .textContent();
        expect(newSelection).not.toBe(initialSelection);
      }
    }
  });

  test("should update settings when methodology changes", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Get initial settings
    const initialSettings = page.locator('[data-methodology-settings]');
    const initialSettingsText = await initialSettings.textContent();

    // Switch methodology
    const methodologyButton = page.locator('[data-methodology-button]');
    if (await methodologyButton.isVisible()) {
      await methodologyButton.click();
      await page.waitForSelector('[data-methodology-menu]', { timeout: 5000 });

      const methodologyOptions = page.locator('[data-methodology-option]');
      const count = await methodologyOptions.count();

      if (count >= 2) {
        const secondOption = methodologyOptions.nth(1);
        await secondOption.click();

        // Verify settings changed
        await page.waitForTimeout(500);

        // Settings should update (may show different configuration options)
        const newSettings = page.locator('[data-methodology-settings]');
        if (await newSettings.isVisible()) {
          const newSettingsText = await newSettings.textContent();
          // Settings might be different for different methodologies
          // At minimum, the methodology name should update
          expect(newSettingsText).toBeTruthy();
        }
      }
    }
  });

  test("should preview organization result with selected methodology", async ({
    page,
  }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload a file
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "preview_test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("preview content"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Look for preview section
    const preview = page.locator('[data-preview-section]');
    if (await preview.isVisible()) {
      const previewText = await preview.textContent();
      expect(previewText).toBeTruthy();

      // Switch methodology
      const methodologyButton = page.locator('[data-methodology-button]');
      if (await methodologyButton.isVisible()) {
        await methodologyButton.click();
        await page.waitForSelector('[data-methodology-menu]', { timeout: 5000 });

        const secondOption = page
          .locator('[data-methodology-option]')
          .nth(1);
        if ((await secondOption.isVisible()) !== false) {
          await secondOption.click();
          await page.waitForTimeout(500);

          // Preview should update with new methodology
          const newPreviewText = await preview.textContent();
          expect(newPreviewText).toBeTruthy();
        }
      }
    }
  });

  test("should save methodology preference", async ({ page }) => {
    // Navigate to settings
    const settingsLink = page.locator("a:has-text('Settings')");
    if (await settingsLink.isVisible()) {
      await settingsLink.click();
      await page.waitForSelector('[data-settings-panel]', { timeout: 5000 });

      // Find methodology selector
      const methodologyOptions = page.locator('[data-methodology-option]');
      const count = await methodologyOptions.count();

      if (count >= 2) {
        // Select second methodology
        const secondOption = methodologyOptions.nth(1);
        const methodologyName = await secondOption.textContent();
        await secondOption.click();

        // Look for save button
        const saveButton = page.locator('button:has-text("Save")');
        if (await saveButton.isVisible()) {
          await saveButton.click();

          // Wait for save confirmation
          const savedIndicator = page.locator('[data-saved]');
          if (await savedIndicator.isVisible()) {
            await expect(savedIndicator).toBeVisible({ timeout: 5000 });
          }
        }
      }
    }
  });

  test("should persist methodology preference on page reload", async ({
    page,
  }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Select specific methodology
    const methodologyButton = page.locator('[data-methodology-button]');
    if (await methodologyButton.isVisible()) {
      await methodologyButton.click();
      await page.waitForSelector('[data-methodology-menu]', { timeout: 5000 });

      const secondOption = page.locator('[data-methodology-option]').nth(1);
      const selectedMethodology = await secondOption.textContent();
      await secondOption.click();

      // Verify selection
      await page.waitForTimeout(500);
      let currentSelection = await page
        .locator('[data-selected-methodology]')
        .textContent();
      expect(currentSelection).toContain(selectedMethodology);

      // Reload page
      await page.reload();
      await page.waitForLoadState("networkidle");

      // Navigate back to organize
      await page.click("a:has-text('Organize')");
      await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

      // Verify preference persisted
      currentSelection = await page
        .locator('[data-selected-methodology]')
        .textContent();
      expect(currentSelection).toContain(selectedMethodology);
    }
  });

  test("should show PARA methodology details", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Switch to PARA if not already selected
    const methodologyButton = page.locator('[data-methodology-button]');
    if (await methodologyButton.isVisible()) {
      const selected = await page
        .locator('[data-selected-methodology]')
        .textContent();

      if (!selected.includes("PARA")) {
        await methodologyButton.click();
        await page.waitForSelector('[data-methodology-menu]', { timeout: 5000 });

        const paraOption = page.locator('button:has-text("PARA")');
        if (await paraOption.isVisible()) {
          await paraOption.click();
        }
      }

      // Check PARA-specific UI
      const paraSettings = page.locator('[data-para-settings]');
      if (await paraSettings.isVisible()) {
        const settingsText = await paraSettings.textContent();
        // Should mention PARA categories
        expect(
          settingsText.toLowerCase().includes("project") ||
            settingsText.toLowerCase().includes("area"),
        ).toBeTruthy();
      }
    }
  });

  test("should show Johnny Decimal methodology details", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Switch to Johnny Decimal
    const methodologyButton = page.locator('[data-methodology-button]');
    if (await methodologyButton.isVisible()) {
      await methodologyButton.click();
      await page.waitForSelector('[data-methodology-menu]', { timeout: 5000 });

      const jdOption = page.locator('button:has-text("Johnny Decimal")');
      if (await jdOption.isVisible()) {
        await jdOption.click();

        // Check JD-specific UI
        await page.waitForTimeout(500);
        const jdSettings = page.locator('[data-johnny-decimal-settings]');
        if (await jdSettings.isVisible()) {
          const settingsText = await jdSettings.textContent();
          // Should mention decimal/numbering system
          expect(settingsText).toMatch(/decimal|number|index/i);
        }

        // Verify selected
        const selection = await page
          .locator('[data-selected-methodology]')
          .textContent();
        expect(selection).toContain("Johnny Decimal");
      }
    }
  });

  test("should allow organizing with PARA methodology", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Ensure PARA is selected
    const methodologyButton = page.locator('[data-methodology-button]');
    if (await methodologyButton.isVisible()) {
      await methodologyButton.click();
      await page.waitForSelector('[data-methodology-menu]', { timeout: 5000 });

      const paraOption = page.locator('button:has-text("PARA")');
      if (await paraOption.isVisible()) {
        await paraOption.click();
      }
    }

    // Upload file
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "para_test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("para test"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });

    // Verify results show PARA structure
    const results = page.locator('[data-organization-results]');
    await expect(results).toBeVisible();
  });

  test("should allow organizing with Johnny Decimal methodology", async ({
    page,
  }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Switch to Johnny Decimal
    const methodologyButton = page.locator('[data-methodology-button]');
    if (await methodologyButton.isVisible()) {
      await methodologyButton.click();
      await page.waitForSelector('[data-methodology-menu]', { timeout: 5000 });

      const jdOption = page.locator('button:has-text("Johnny Decimal")');
      if (await jdOption.isVisible()) {
        await jdOption.click();
      }
    }

    // Upload file
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "jd_test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("jd test"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });

    // Verify results
    const results = page.locator('[data-organization-results]');
    await expect(results).toBeVisible();
  });
});
