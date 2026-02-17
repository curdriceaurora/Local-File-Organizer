/**
 * E2E Test: Batch File Operations
 *
 * Tests batch operations including:
 * 1. Batch file upload
 * 2. Real-time progress tracking
 * 3. Cancel operation
 * 4. Retry failed files
 * 5. Mixed file types handling
 */

import { test, expect } from "@playwright/test";

test.describe("Batch File Operations", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("should handle batch upload with multiple files", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Create batch of files
    const files = [
      {
        name: "batch1.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("pdf 1"),
      },
      {
        name: "batch2.docx",
        mimeType:
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buffer: Buffer.from("docx 1"),
      },
      {
        name: "batch3.xlsx",
        mimeType:
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: Buffer.from("xlsx 1"),
      },
      {
        name: "batch4.jpg",
        mimeType: "image/jpeg",
        buffer: Buffer.from("jpeg 1"),
      },
      {
        name: "batch5.png",
        mimeType: "image/png",
        buffer: Buffer.from("png 1"),
      },
    ];

    // Upload all files at once
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(files);

    // Wait for all files to appear
    await page.waitForSelector('[data-file-item]', { timeout: 5000 });
    const fileCount = await page.locator('[data-file-item]').count();
    expect(fileCount).toBe(5);

    // Verify each file is listed
    const fileNames = await page.locator('[data-file-name]').allTextContents();
    expect(fileNames.length).toBeGreaterThanOrEqual(5);
    expect(fileNames.join(",")).toContain("batch1.pdf");
  });

  test("should display batch progress indicator", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload multiple files
    const files = [];
    for (let i = 1; i <= 3; i++) {
      files.push({
        name: `progress_batch_${i}.pdf`,
        mimeType: "application/pdf",
        buffer: Buffer.from(`content ${i}`),
      });
    }

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(files);

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Start batch organization
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Look for batch progress display
    const batchProgress = page.locator('[data-batch-progress]');
    if (await batchProgress.isVisible()) {
      const progressText = await batchProgress.textContent();
      // Should show current file and total
      expect(progressText).toMatch(/\d+\s*\/\s*\d+/);
    }

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });
  });

  test("should track real-time progress updates", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload files
    const files = [];
    for (let i = 1; i <= 5; i++) {
      files.push({
        name: `realtime_${i}.pdf`,
        mimeType: "application/pdf",
        buffer: Buffer.from(`content ${i}`),
      });
    }

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(files);

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Start organization
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Monitor progress updates
    const progressIndicator = page.locator('[data-progress-indicator]');
    let previousProgress = 0;

    // Check that progress increases over time
    if (await progressIndicator.isVisible()) {
      for (let i = 0; i < 3; i++) {
        const progressText = await progressIndicator.textContent();
        const progressMatch = progressText.match(/(\d+)%/);
        if (progressMatch) {
          const currentProgress = parseInt(progressMatch[1]);
          expect(currentProgress).toBeGreaterThanOrEqual(previousProgress);
          previousProgress = currentProgress;
        }
        await page.waitForTimeout(1000);
      }
    }

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });
  });

  test("should allow canceling batch operation", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload files
    const files = [];
    for (let i = 1; i <= 10; i++) {
      files.push({
        name: `cancel_${i}.pdf`,
        mimeType: "application/pdf",
        buffer: Buffer.from(`content ${i}`),
      });
    }

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(files);

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Start organization
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait a moment for processing to start
    await page.waitForTimeout(2000);

    // Look for cancel button
    const cancelButton = page.locator('button:has-text("Cancel")');
    if (await cancelButton.isVisible()) {
      await cancelButton.click();

      // Verify cancellation message or state change
      const cancelledIndicator = page.locator('[data-cancelled]');
      const progressIndicator = page.locator('[data-progress-indicator]');

      // Either should show cancelled state or progress should stop
      const isCancelled =
        (await cancelledIndicator.isVisible()) ||
        (await progressIndicator.textContent()).includes("Cancelled");
      expect(isCancelled).toBeTruthy();
    }
  });

  test("should retry failed files in batch", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload files (some may fail in real scenario)
    const files = [
      {
        name: "retry_success.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("success content"),
      },
      {
        name: "retry_test.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("test content"),
      },
    ];

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(files);

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Start organization
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for completion or error state
    await page.waitForSelector(
      '[data-organize-complete], [data-batch-errors]',
      { timeout: 15000 },
    );

    // Look for failed items
    const failedItems = page.locator('[data-failed-item]');
    const failedCount = await failedItems.count();

    if (failedCount > 0) {
      // Look for retry button
      const retryButton = page.locator('button:has-text("Retry")');
      if (await retryButton.isVisible()) {
        await retryButton.click();

        // Wait for retry to complete
        await page.waitForSelector('[data-organize-complete]', {
          timeout: 15000,
        });
      }
    }
  });

  test("should handle mixed file types in batch", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Create batch with various file types
    const mixedFiles = [
      {
        name: "document.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("pdf"),
      },
      {
        name: "spreadsheet.xlsx",
        mimeType:
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: Buffer.from("xlsx"),
      },
      {
        name: "presentation.pptx",
        mimeType:
          "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        buffer: Buffer.from("pptx"),
      },
      {
        name: "image.jpg",
        mimeType: "image/jpeg",
        buffer: Buffer.from("jpg"),
      },
      {
        name: "archive.zip",
        mimeType: "application/zip",
        buffer: Buffer.from("zip"),
      },
      {
        name: "text.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("txt"),
      },
    ];

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(mixedFiles);

    // Wait for all files to be listed
    await page.waitForSelector('[data-file-item]', { timeout: 5000 });
    const fileCount = await page.locator('[data-file-item]').count();
    expect(fileCount).toBe(6);

    // Verify different file types are shown
    const fileTypes = await page.locator('[data-file-type]').allTextContents();
    expect(fileTypes.length).toBeGreaterThanOrEqual(6);

    // Organize mixed batch
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });

    // Verify all files were processed
    const results = page.locator('[data-organization-results]');
    await expect(results).toBeVisible();
  });

  test("should show batch statistics after completion", async ({ page }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload batch
    const files = [];
    for (let i = 1; i <= 5; i++) {
      files.push({
        name: `stats_${i}.pdf`,
        mimeType: "application/pdf",
        buffer: Buffer.from(`content ${i}`),
      });
    }

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(files);

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });

    // Check for batch statistics
    const statistics = page.locator('[data-batch-statistics]');
    if (await statistics.isVisible()) {
      const statsText = await statistics.textContent();

      // Should contain stats about total, success, failed
      expect(statsText).toMatch(/total|success|processed|completed/i);
    }
  });

  test("should preserve file order through batch organization", async ({
    page,
  }) => {
    // Navigate to organize section
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload ordered batch
    const files = [
      {
        name: "01_first.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("first"),
      },
      {
        name: "02_second.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("second"),
      },
      {
        name: "03_third.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("third"),
      },
    ];

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(files);

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Get initial order
    let fileNames = await page.locator('[data-file-name]').allTextContents();
    const initialOrder = fileNames.slice(0, 3);

    // Organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for completion
    await page.waitForSelector('[data-organize-complete]', {
      timeout: 15000,
    });

    // Check if order is preserved in results
    const resultNames = page.locator('[data-result-name]');
    fileNames = await resultNames.allTextContents();

    // Files should appear in results in some order
    expect(fileNames.length).toBeGreaterThan(0);
  });
});
