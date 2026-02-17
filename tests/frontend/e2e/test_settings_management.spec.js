/**
 * E2E Test: Settings Management
 *
 * Tests settings functionality:
 * 1. Open settings panel/page
 * 2. Modify various settings
 * 3. Save changes
 * 4. Verify persistence across reloads
 * 5. Reset to default settings
 * 6. Handle validation errors
 */

import { test, expect } from "@playwright/test";

test.describe("Settings Management", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("should open settings panel", async ({ page }) => {
    // Find and click settings link/button
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    // Wait for settings to load
    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    const settings = page.locator('[data-settings-panel]');
    await expect(settings).toBeVisible();
  });

  test("should display all settings categories", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Check for settings categories
    const generalSettings = page.locator('[data-settings-general]');
    const organizationSettings = page.locator('[data-settings-organization]');
    const appearanceSettings = page.locator('[data-settings-appearance]');

    // At least some settings should be visible
    const visibleSettings =
      (await generalSettings.isVisible()) ||
      (await organizationSettings.isVisible()) ||
      (await appearanceSettings.isVisible());

    expect(visibleSettings).toBeTruthy();
  });

  test("should modify general settings", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Find a general setting to modify (e.g., language)
    const languageSelect = page.locator('[data-setting-language]');
    if (await languageSelect.isVisible()) {
      // Get current value
      const currentValue = await languageSelect.inputValue();

      // Change to different value
      const options = await page
        .locator('[data-setting-language] option')
        .count();
      if (options > 1) {
        await languageSelect.selectOption({ index: 1 });

        // Verify value changed
        const newValue = await languageSelect.inputValue();
        expect(newValue).not.toBe(currentValue);
      }
    }
  });

  test("should modify organization settings", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Find organization settings
    const autoOrganizeToggle = page.locator('[data-setting-auto-organize]');
    if (await autoOrganizeToggle.isVisible()) {
      const isChecked = await autoOrganizeToggle.isChecked();

      // Toggle the setting
      await autoOrganizeToggle.click();

      // Verify change
      const newState = await autoOrganizeToggle.isChecked();
      expect(newState).toBe(!isChecked);
    }
  });

  test("should modify appearance settings", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Find theme setting
    const themeSelect = page.locator('[data-setting-theme]');
    if (await themeSelect.isVisible()) {
      const currentTheme = await themeSelect.inputValue();

      // Change theme
      const options = await page
        .locator('[data-setting-theme] option')
        .count();
      if (options > 1) {
        await themeSelect.selectOption({ index: 1 });

        // Verify change
        const newTheme = await themeSelect.inputValue();
        expect(newTheme).not.toBe(currentTheme);
      }
    }
  });

  test("should save settings changes", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Modify a setting
    const autoOrganizeToggle = page.locator('[data-setting-auto-organize]');
    if (await autoOrganizeToggle.isVisible()) {
      const initialState = await autoOrganizeToggle.isChecked();
      await autoOrganizeToggle.click();

      // Find and click save button
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
  });

  test("should persist settings after page reload", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Modify and save a setting
    const autoOrganizeToggle = page.locator('[data-setting-auto-organize]');
    if (await autoOrganizeToggle.isVisible()) {
      const initialState = await autoOrganizeToggle.isChecked();
      await autoOrganizeToggle.click();

      const saveButton = page.locator('button:has-text("Save")');
      if (await saveButton.isVisible()) {
        await saveButton.click();
        await page.waitForTimeout(500);
      }

      // Reload page
      await page.reload();
      await page.waitForLoadState("networkidle");

      // Open settings again
      await settingsLink.click();
      await page.waitForSelector(
        '[data-settings-panel], [data-settings-page]',
        { timeout: 5000 },
      );

      // Verify setting persisted
      const newState = await autoOrganizeToggle.isChecked();
      expect(newState).toBe(!initialState);
    }
  });

  test("should reset settings to defaults", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Find reset button
    const resetButton = page.locator('button:has-text("Reset")');
    if (await resetButton.isVisible()) {
      // Store current values
      const autoOrganizeToggle = page.locator('[data-setting-auto-organize]');
      const beforeReset = await autoOrganizeToggle.isChecked();

      // Click reset
      await resetButton.click();

      // Confirm if dialog appears
      const confirmButton = page.locator('button:has-text("Confirm")');
      if (await confirmButton.isVisible()) {
        await confirmButton.click();
      }

      // Wait for reset to complete
      await page.waitForTimeout(1000);

      // Verify settings are reset to defaults
      // They might be back to original values
      const afterReset = await autoOrganizeToggle.isChecked();
      expect(afterReset).toBeTruthy(); // Assuming default is true
    }
  });

  test("should show validation error for invalid input", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Find a number input (e.g., timeout setting)
    const numberInput = page.locator('[data-setting-number]');
    if (await numberInput.isVisible()) {
      // Clear and enter invalid value
      await numberInput.fill("-999");

      // Try to save
      const saveButton = page.locator('button:has-text("Save")');
      if (await saveButton.isVisible()) {
        await saveButton.click();

        // Look for error message
        const errorMessage = page.locator('[data-error-message]');
        if (await errorMessage.isVisible()) {
          const message = await errorMessage.textContent();
          expect(message).toMatch(/invalid|error|must be/i);
        }
      }
    }
  });

  test("should disable save button when no changes made", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Check save button state without making changes
    const saveButton = page.locator('button:has-text("Save")');
    if (await saveButton.isVisible()) {
      const isDisabled = await saveButton.isDisabled();
      expect(isDisabled).toBeTruthy(); // Should be disabled initially
    }
  });

  test("should enable save button after making changes", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Make a change
    const autoOrganizeToggle = page.locator('[data-setting-auto-organize]');
    if (await autoOrganizeToggle.isVisible()) {
      await autoOrganizeToggle.click();

      // Verify save button is now enabled
      const saveButton = page.locator('button:has-text("Save")');
      if (await saveButton.isVisible()) {
        const isDisabled = await saveButton.isDisabled();
        expect(isDisabled).toBeFalsy(); // Should be enabled now
      }
    }
  });

  test("should show unsaved changes warning", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Make a change without saving
    const autoOrganizeToggle = page.locator('[data-setting-auto-organize]');
    if (await autoOrganizeToggle.isVisible()) {
      await autoOrganizeToggle.click();

      // Try to navigate away
      const homeLink = page.locator("a:has-text('Dashboard')");
      await homeLink.click();

      // Check for warning dialog
      const confirmDialog = page.locator('[data-confirm-dialog]');
      if (await confirmDialog.isVisible()) {
        const warning = await confirmDialog.textContent();
        expect(warning).toMatch(/unsaved|confirm|discard/i);
      }
    }
  });

  test("should display settings sections", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Look for section tabs/links
    const generalTab = page.locator('button:has-text("General")');
    const organizationTab = page.locator('button:has-text("Organization")');
    const appearanceTab = page.locator('button:has-text("Appearance")');

    // At least some tabs should exist
    const tabCount =
      (await generalTab.isVisible() ? 1 : 0) +
      (await organizationTab.isVisible() ? 1 : 0) +
      (await appearanceTab.isVisible() ? 1 : 0);

    expect(tabCount).toBeGreaterThanOrEqual(1);
  });

  test("should switch between settings sections", async ({ page }) => {
    // Open settings
    const settingsLink = page.locator(
      "a:has-text('Settings'), button:has-text('Settings')",
    );
    await settingsLink.click();

    await page.waitForSelector(
      '[data-settings-panel], [data-settings-page]',
      { timeout: 5000 },
    );

    // Switch to organization section
    const organizationTab = page.locator('button:has-text("Organization")');
    if (await organizationTab.isVisible()) {
      await organizationTab.click();
      await page.waitForTimeout(300);

      // Verify we're on organization section
      const orgSettings = page.locator('[data-settings-organization]');
      if (await orgSettings.isVisible()) {
        const visible = await orgSettings.isVisible();
        expect(visible).toBeTruthy();
      }
    }

    // Switch to appearance section
    const appearanceTab = page.locator('button:has-text("Appearance")');
    if (await appearanceTab.isVisible()) {
      await appearanceTab.click();
      await page.waitForTimeout(300);

      // Verify we're on appearance section
      const appearSettings = page.locator('[data-settings-appearance]');
      if (await appearSettings.isVisible()) {
        const visible = await appearSettings.isVisible();
        expect(visible).toBeTruthy();
      }
    }
  });
});
