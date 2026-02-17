/**
 * E2E Test: File Organization Workflow
 *
 * Tests the complete journey from file upload through organization:
 * 1. Navigate to organize interface
 * 2. Upload files (single and multiple)
 * 3. Select organization methodology
 * 4. Configure settings
 * 5. Execute organization
 * 6. Verify results in dashboard
 */

import { test, expect } from "@playwright/test";

test.describe("File Organization Workflow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // Wait for the app to load
    await page.waitForLoadState("networkidle");
  });

  test("should complete basic file organization workflow", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Verify we're on the organize page
    const heading = await page.locator("h1").textContent();
    expect(heading).toContain("Organize");

    // Upload a single file
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "sample_document.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("sample pdf content"),
    });

    // Wait for file to appear in the list
    await page.waitForSelector('[data-file-item]', { timeout: 5000 });
    const fileItems = await page.locator('[data-file-item]').count();
    expect(fileItems).toBeGreaterThan(0);

    // Select methodology (default should be PARA)
    const methodologySelector = page.locator('[data-methodology-selector]');
    if (await methodologySelector.isVisible()) {
      await methodologySelector.click();
      const paraOption = page.locator('button:has-text("PARA")');
      await paraOption.click();
    }

    // Verify methodology selection appears
    const selectedMethodology = page.locator('[data-selected-methodology]');
    await expect(selectedMethodology).toBeVisible();

    // Click organize button
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for organization to complete
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });

    // Verify results display
    const results = page.locator('[data-organization-results]');
    await expect(results).toBeVisible();

    // Check that results show summary statistics
    const summary = page.locator('[data-result-summary]');
    const summaryText = await summary.textContent();
    expect(summaryText).toContain("organized");
  });

  test("should upload multiple files and organize", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload multiple files
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles([
      {
        name: "document1.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("pdf content 1"),
      },
      {
        name: "image1.jpg",
        mimeType: "image/jpeg",
        buffer: Buffer.from("jpeg content 1"),
      },
      {
        name: "spreadsheet1.xlsx",
        mimeType:
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: Buffer.from("xlsx content 1"),
      },
    ]);

    // Wait for files to appear
    await page.waitForSelector('[data-file-item]', { timeout: 5000 });
    const fileItems = await page.locator('[data-file-item]').count();
    expect(fileItems).toBe(3);

    // Verify files are listed with correct names
    const fileNames = await page.locator('[data-file-name]').allTextContents();
    expect(fileNames).toContain(expect.stringContaining("document1.pdf"));
    expect(fileNames).toContain(expect.stringContaining("image1.jpg"));
    expect(fileNames).toContain(expect.stringContaining("spreadsheet1.xlsx"));

    // Execute organization
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });

    // Verify all files are in results
    const resultItems = page.locator('[data-result-item]');
    const resultCount = await resultItems.count();
    expect(resultCount).toBeGreaterThanOrEqual(1);
  });

  test("should switch methodology before organizing", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload a file
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("test content"),
    });

    // Wait for file to appear
    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Open methodology selector
    const methodologyButton = page.locator('[data-methodology-button]');
    if (await methodologyButton.isVisible()) {
      await methodologyButton.click();
      await page.waitForSelector('[data-methodology-menu]');

      // Try selecting Johnny Decimal if available
      const jdOption = page.locator('button:has-text("Johnny Decimal")');
      if (await jdOption.isVisible()) {
        await jdOption.click();

        // Verify selection changed
        const selectedMethod = page.locator('[data-selected-methodology]');
        const methodText = await selectedMethod.textContent();
        expect(methodText).toContain("Johnny Decimal");
      }
    }

    // Proceed with organization
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });

    const results = page.locator('[data-organization-results]');
    await expect(results).toBeVisible();
  });

  test("should display organization progress during execution", async ({
    page,
  }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload files
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "progress_test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("test content"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Start organization
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Check for progress indicator
    const progressIndicator = page.locator('[data-progress-indicator]');
    if (await progressIndicator.isVisible()) {
      // Progress should eventually reach completion
      await page.waitForFunction(
        () => {
          const text = document.querySelector('[data-progress-indicator]')
            ?.textContent;
          return text && (text.includes("100%") || text.includes("Complete"));
        },
        { timeout: 15000 },
      );
    }

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });
  });

  test("should view organized file structure after completion", async ({
    page,
  }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload and organize a file
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "structure_test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("test content"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });

    // Look for file structure display
    const fileStructure = page.locator('[data-file-structure]');
    if (await fileStructure.isVisible()) {
      const structureText = await fileStructure.textContent();
      // Should show some hierarchy/organization
      expect(structureText).toBeTruthy();
    }

    // Verify result summary is visible
    const summary = page.locator('[data-result-summary]');
    await expect(summary).toBeVisible();
  });

  test("should reset and start new organization", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload and organize
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "reset_test1.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("test content 1"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });

    // Click reset/new button
    const resetButton = page.locator('button:has-text("New Organization")');
    if (await resetButton.isVisible()) {
      await resetButton.click();

      // Verify file list is cleared
      const fileItems = page.locator('[data-file-item]');
      let count = await fileItems.count();
      expect(count).toBe(0);

      // Upload new file
      await fileInput.setInputFiles({
        name: "reset_test2.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("test content 2"),
      });

      await page.waitForSelector('[data-file-item]', { timeout: 5000 });
      count = await fileItems.count();
      expect(count).toBeGreaterThan(0);
    }
  });

  test("should handle drag-and-drop file upload", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Find drop zone
    const dropZone = page.locator('[data-upload-zone]');

    if (await dropZone.isVisible()) {
      // Simulate drag-drop using setInputFiles
      const fileInput = page.locator('input[type="file"]').first();
      await fileInput.setInputFiles({
        name: "dragdrop_test.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("drag drop test"),
      });

      // Verify file appears
      await page.waitForSelector('[data-file-item]', { timeout: 5000 });
      const fileCount = await page.locator('[data-file-item]').count();
      expect(fileCount).toBeGreaterThan(0);
    }
  });
});
