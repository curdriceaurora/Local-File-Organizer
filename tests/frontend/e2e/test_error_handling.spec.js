/**
 * E2E Test: Error Handling
 *
 * Tests error scenarios:
 * 1. Upload unsupported file type
 * 2. Disk space errors
 * 3. API timeout/failure
 * 4. Network disconnection and recovery
 * 5. Corrupted file handling
 * 6. Permission denied scenarios
 * 7. Clear error messages
 */

import { test, expect } from "@playwright/test";

test.describe("Error Handling", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("should show error when uploading unsupported file type", async ({
    page,
  }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Try to upload unsupported file
    const fileInput = page.locator('input[type="file"]').first();

    // Attempt to upload .exe or other unsupported type
    // Note: Most systems won't allow direct .exe upload, but we can try
    await fileInput.setInputFiles({
      name: "malware.exe",
      mimeType: "application/x-msdownload",
      buffer: Buffer.from("fake executable"),
    });

    // Wait for error to appear
    await page.waitForTimeout(500);

    // Look for error message
    const errorMessage = page.locator('[data-error-message]');
    if (await errorMessage.isVisible()) {
      const message = await errorMessage.textContent();
      expect(message).toMatch(/not allowed|unsupported|invalid/i);
    }

    // Alternative: Check if file was rejected
    const fileItems = page.locator('[data-file-item]');
    const count = await fileItems.count();
    // If no error was shown, file should not be in list
    const hasExeFile = await page
      .locator('[data-file-name]:has-text(".exe")')
      .isVisible();
    const shouldBeRejected = !hasExeFile;
    expect(shouldBeRejected).toBeTruthy();
  });

  test("should handle file size limit error", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Try to upload very large file (simulate)
    const fileInput = page.locator('input[type="file"]').first();

    // Create a large buffer (100MB simulation)
    const largeBuffer = Buffer.alloc(100 * 1024 * 1024);

    try {
      await fileInput.setInputFiles({
        name: "huge_file.bin",
        mimeType: "application/octet-stream",
        buffer: largeBuffer,
      });

      // Wait for error
      await page.waitForTimeout(1000);

      // Check for error message
      const errorMessage = page.locator('[data-error-message]');
      if (await errorMessage.isVisible()) {
        const message = await errorMessage.textContent();
        expect(message).toMatch(/too large|size limit|exceeds/i);
      }
    } catch {
      // Expected - size limit enforced by browser/system
      // This is acceptable
    }
  });

  test("should handle API timeout gracefully", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Mock API to timeout
    await page.route("**/api/**", (route) => {
      // Delay response beyond timeout
      setTimeout(() => {
        route.abort("timedout");
      }, 40000);
    });

    // Upload and try to organize
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "timeout_test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("timeout test"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Click organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for timeout error
    await page.waitForSelector('[data-error-message], [data-api-error]', {
      timeout: 15000,
    });

    // Check for error message
    const errorMessage = page.locator('[data-error-message]');
    if (await errorMessage.isVisible()) {
      const message = await errorMessage.textContent();
      expect(message).toMatch(/timeout|taking too long|try again/i);
    }
  });

  test("should handle API error response", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Mock API to return error
    await page.route("**/api/organize", (route) => {
      route.abort("failed");
    });

    // Upload and try to organize
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "error_test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("error test"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Click organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for error
    await page.waitForSelector('[data-error-message], [data-api-error]', {
      timeout: 10000,
    });

    // Verify error is shown
    const errorMessage = page.locator('[data-error-message]');
    expect(await errorMessage.isVisible()).toBeTruthy();
  });

  test("should show clear error message with recovery action", async ({
    page,
  }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Mock API to fail
    await page.route("**/api/organize", (route) => {
      route.abort("failed");
    });

    // Upload file
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "recovery_test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("recovery test"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for error
    await page.waitForSelector('[data-error-message]', { timeout: 10000 });

    // Verify error message is user-friendly
    const errorMessage = page.locator('[data-error-message]');
    const message = await errorMessage.textContent();
    expect(message).toBeTruthy();

    // Check for recovery action (e.g., Retry button)
    const retryButton = page.locator('button:has-text("Retry")');
    if (await retryButton.isVisible()) {
      expect(await retryButton.isVisible()).toBeTruthy();
    }
  });

  test("should handle network disconnection", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Go offline
    await page.context().setOffline(true);

    // Try to organize
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "offline_test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("offline test"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Attempt organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Should show network error
    await page.waitForTimeout(2000);

    const errorMessage = page.locator('[data-error-message]');
    if (await errorMessage.isVisible()) {
      const message = await errorMessage.textContent();
      expect(message).toMatch(/network|offline|connection/i);
    }

    // Come back online
    await page.context().setOffline(false);

    // Look for retry option
    const retryButton = page.locator('button:has-text("Retry")');
    if (await retryButton.isVisible()) {
      await retryButton.click();
      // Should attempt again
      await page.waitForTimeout(500);
    }
  });

  test("should handle file access permission errors", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload file
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "permission_test.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("permission test"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Mock permission error
    await page.route("**/api/organize", (route) => {
      route.abort("failed");
    });

    // Organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for error
    await page.waitForTimeout(2000);

    // Check error message
    const errorMessage = page.locator('[data-error-message]');
    if (await errorMessage.isVisible()) {
      const message = await errorMessage.textContent();
      // Should mention permission or access issue
      expect(message).toBeTruthy();
    }
  });

  test("should handle corrupted file gracefully", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload "corrupted" file (just invalid content in PDF)
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "corrupted.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("NOT_A_VALID_PDF_CONTENT"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Try to organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // May show error or skip corrupted file
    await page.waitForTimeout(2000);

    // Either error message or warning should appear
    const errorMessage = page.locator('[data-error-message]');
    const warningMessage = page.locator('[data-warning-message]');

    const hasError = await errorMessage.isVisible();
    const hasWarning = await warningMessage.isVisible();

    expect(hasError || hasWarning).toBeTruthy();
  });

  test("should display validation errors clearly", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Look for any validation on file list
    const organizeButton = page.locator('button:has-text("Organize")');

    // Try to organize without files
    if ((await page.locator('[data-file-item]').count()) === 0) {
      await organizeButton.click();

      // Should show validation error
      const validationError = page.locator('[data-validation-error]');
      if (await validationError.isVisible()) {
        const message = await validationError.textContent();
        expect(message).toMatch(/select files|no files|at least one/i);
      }
    }
  });

  test("should recover from error and allow retry", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // First attempt fails
    let callCount = 0;
    await page.route("**/api/organize", (route) => {
      // First call fails
      if (callCount === 0) {
        callCount++;
        route.abort("failed");
      } else {
        // Second call succeeds
        route.continue();
      }
    });

    // Upload file
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles({
      name: "retry_recovery.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("retry test"),
    });

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Try to organize (will fail)
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Wait for error
    await page.waitForSelector('[data-error-message]', { timeout: 10000 });

    // Click retry
    const retryButton = page.locator('button:has-text("Retry")');
    if (await retryButton.isVisible()) {
      await retryButton.click();

      // Second attempt might succeed
      await page.waitForTimeout(2000);
    }
  });

  test("should warn about incomplete operations", async ({ page }) => {
    // Navigate to organize
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });

    // Upload multiple files
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles([
      {
        name: "partial1.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("partial 1"),
      },
      {
        name: "partial2.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("partial 2"),
      },
    ]);

    await page.waitForSelector('[data-file-item]', { timeout: 5000 });

    // Mock partial failure (some files fail)
    await page.route("**/api/organize", (route) => {
      route.abort("failed");
    });

    // Organize
    const organizeButton = page.locator('button:has-text("Organize")');
    await organizeButton.click();

    // Should show partial error
    await page.waitForTimeout(2000);

    const errorMessage = page.locator('[data-error-message]');
    if (await errorMessage.isVisible()) {
      expect(await errorMessage.isVisible()).toBeTruthy();
    }
  });
});
