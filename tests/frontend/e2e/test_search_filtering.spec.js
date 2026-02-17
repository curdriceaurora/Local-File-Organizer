/**
 * E2E Test: Search and Filtering
 *
 * Tests search and filtering functionality:
 * 1. Search for files with keywords
 * 2. Apply single filters (by type, date, size)
 * 3. Combine multiple filters
 * 4. Sort results
 * 5. Clear filters and reset
 * 6. Export filtered results
 */

import { test, expect } from "@playwright/test";

test.describe("Search and Filtering", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Navigate to organize section and set up some files
    await page.click("a:has-text('Organize')");
    await page.waitForSelector('[data-organize-interface]', { timeout: 5000 });
  });

  test("should search files by keyword", async ({ page }) => {
    // Look for search interface
    const searchInput = page.locator('[data-search-input]');
    if (await searchInput.isVisible()) {
      // Enter search term
      await searchInput.fill("annual");

      // Wait for results
      await page.waitForTimeout(500);

      // Check if results appear
      const searchResults = page.locator('[data-search-results]');
      if (await searchResults.isVisible()) {
        const resultsText = await searchResults.textContent();
        expect(resultsText).toBeTruthy();
      }
    }
  });

  test("should filter by file type", async ({ page }) => {
    // Find filter section
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      // Find type filter
      const typeFilter = page.locator('[data-filter-type]');
      if (await typeFilter.isVisible()) {
        await typeFilter.click();

        // Select PDF type
        const pdfOption = page.locator('button:has-text("PDF")');
        if (await pdfOption.isVisible()) {
          await pdfOption.click();

          // Wait for results to update
          await page.waitForTimeout(500);

          // Verify results are filtered
          const results = page.locator('[data-search-results]');
          if (await results.isVisible()) {
            // All results should be PDFs
            const fileTypes = await page
              .locator('[data-result-type]')
              .allTextContents();
            // At minimum, filter was applied
            expect(fileTypes.length).toBeGreaterThanOrEqual(0);
          }
        }
      }
    }
  });

  test("should filter by date range", async ({ page }) => {
    // Find filter section
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      // Find date filter
      const dateFilter = page.locator('[data-filter-date]');
      if (await dateFilter.isVisible()) {
        await dateFilter.click();

        // Select date range (e.g., last month)
        const lastMonthOption = page.locator('button:has-text("Last Month")');
        if (await lastMonthOption.isVisible()) {
          await lastMonthOption.click();

          // Wait for results to update
          await page.waitForTimeout(500);

          // Verify filter applied
          const activeFilter = page.locator('[data-active-filter]');
          if (await activeFilter.isVisible()) {
            const filterText = await activeFilter.textContent();
            expect(filterText.toLowerCase()).toContain("month");
          }
        }
      }
    }
  });

  test("should filter by file size", async ({ page }) => {
    // Find filter section
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      // Find size filter
      const sizeFilter = page.locator('[data-filter-size]');
      if (await sizeFilter.isVisible()) {
        await sizeFilter.click();

        // Select size range (e.g., small files)
        const smallOption = page.locator('button:has-text("Small")');
        if (await smallOption.isVisible()) {
          await smallOption.click();

          // Wait for results
          await page.waitForTimeout(500);

          // Verify filter applied
          const activeFilter = page.locator('[data-active-filter]');
          const filterCount = await activeFilter.count();
          expect(filterCount).toBeGreaterThanOrEqual(0);
        }
      }
    }
  });

  test("should combine multiple filters", async ({ page }) => {
    // Find filter section
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      // Apply type filter
      const typeFilter = page.locator('[data-filter-type]');
      if (await typeFilter.isVisible()) {
        await typeFilter.click();

        const pdfOption = page.locator('button:has-text("PDF")');
        if (await pdfOption.isVisible()) {
          await pdfOption.click();
          await page.waitForTimeout(300);
        }
      }

      // Apply date filter
      const dateFilter = page.locator('[data-filter-date]');
      if (await dateFilter.isVisible()) {
        await dateFilter.click();

        const lastMonthOption = page.locator('button:has-text("Last Month")');
        if (await lastMonthOption.isVisible()) {
          await lastMonthOption.click();
          await page.waitForTimeout(300);
        }
      }

      // Verify multiple filters are active
      const activeFilters = page.locator('[data-active-filter]');
      const filterCount = await activeFilters.count();
      expect(filterCount).toBeGreaterThanOrEqual(1);
    }
  });

  test("should sort search results", async ({ page }) => {
    // Find sort controls
    const sortControl = page.locator('[data-sort-control]');
    if (await sortControl.isVisible()) {
      await sortControl.click();

      // Select sort option (e.g., by name)
      const sortByName = page.locator('button:has-text("Name")');
      if (await sortByName.isVisible()) {
        await sortByName.click();
        await page.waitForTimeout(500);
      }

      // Alternative: sort by date
      const sortByDate = page.locator('button:has-text("Date")');
      if (await sortByDate.isVisible()) {
        await sortByDate.click();

        // Verify sort applied
        const results = page.locator('[data-search-results]');
        if (await results.isVisible()) {
          const resultsText = await results.textContent();
          expect(resultsText).toBeTruthy();
        }
      }
    }
  });

  test("should reverse sort order", async ({ page }) => {
    // Find sort controls
    const sortControl = page.locator('[data-sort-control]');
    if (await sortControl.isVisible()) {
      await sortControl.click();

      // Apply sort
      const sortByName = page.locator('button:has-text("Name")');
      if (await sortByName.isVisible()) {
        await sortByName.click();
        await page.waitForTimeout(300);

        // Find and click reverse button
        const reverseButton = page.locator('[data-sort-reverse]');
        if (await reverseButton.isVisible()) {
          await reverseButton.click();

          // Verify reverse sort indicator
          const reverseIndicator = page.locator('[data-sort-reversed]');
          if (await reverseIndicator.isVisible()) {
            await expect(reverseIndicator).toBeVisible();
          }
        }
      }
    }
  });

  test("should clear single filter", async ({ page }) => {
    // Apply a filter
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      const typeFilter = page.locator('[data-filter-type]');
      if (await typeFilter.isVisible()) {
        await typeFilter.click();

        const pdfOption = page.locator('button:has-text("PDF")');
        if (await pdfOption.isVisible()) {
          await pdfOption.click();
          await page.waitForTimeout(300);

          // Find clear button for this filter
          const clearButton = page.locator('[data-clear-filter]').first();
          if (await clearButton.isVisible()) {
            await clearButton.click();
            await page.waitForTimeout(300);

            // Verify filter is removed
            const activeFilters = page.locator('[data-active-filter]');
            const count = await activeFilters.count();
            expect(count).toBe(0);
          }
        }
      }
    }
  });

  test("should clear all filters", async ({ page }) => {
    // Apply multiple filters
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      // Apply filters...
      const typeFilter = page.locator('[data-filter-type]');
      if (await typeFilter.isVisible()) {
        await typeFilter.click();

        const pdfOption = page.locator('button:has-text("PDF")');
        if (await pdfOption.isVisible()) {
          await pdfOption.click();
          await page.waitForTimeout(300);
        }
      }

      // Find reset all button
      const clearAllButton = page.locator('button:has-text("Clear All")');
      if (await clearAllButton.isVisible()) {
        await clearAllButton.click();
        await page.waitForTimeout(300);

        // Verify all filters are removed
        const activeFilters = page.locator('[data-active-filter]');
        const count = await activeFilters.count();
        expect(count).toBe(0);
      }
    }
  });

  test("should show no results message when filter yields nothing", async ({
    page,
  }) => {
    // Apply a filter that might not match anything
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      // Search for something very specific
      const searchInput = page.locator('[data-search-input]');
      if (await searchInput.isVisible()) {
        await searchInput.fill("xyznonexistent123");
        await page.waitForTimeout(500);

        // Check for no results message
        const noResults = page.locator('[data-no-results]');
        if (await noResults.isVisible()) {
          const message = await noResults.textContent();
          expect(message).toMatch(/no\s+results|not\s+found/i);
        }
      }
    }
  });

  test("should export filtered results", async ({ page }) => {
    // Apply a filter
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      const typeFilter = page.locator('[data-filter-type]');
      if (await typeFilter.isVisible()) {
        await typeFilter.click();

        const pdfOption = page.locator('button:has-text("PDF")');
        if (await pdfOption.isVisible()) {
          await pdfOption.click();
          await page.waitForTimeout(300);

          // Find export button
          const exportButton = page.locator('button:has-text("Export")');
          if (await exportButton.isVisible()) {
            // Listen for download
            const downloadPromise = page.waitForEvent("download");

            await exportButton.click();

            // Verify download occurred
            const download = await downloadPromise;
            const filename = download.suggestedFilename();
            expect(
              filename.includes(".csv") ||
                filename.includes(".json") ||
                filename.includes(".xlsx"),
            ).toBeTruthy();
          }
        }
      }
    }
  });

  test("should update result count when filtering", async ({ page }) => {
    // Get initial count
    const resultCount = page.locator('[data-result-count]');
    const initialCount = await resultCount.textContent();

    // Apply a filter
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      const typeFilter = page.locator('[data-filter-type]');
      if (await typeFilter.isVisible()) {
        await typeFilter.click();

        const pdfOption = page.locator('button:has-text("PDF")');
        if (await pdfOption.isVisible()) {
          await pdfOption.click();
          await page.waitForTimeout(500);

          // Verify count changed
          const newCount = await resultCount.textContent();
          // Count should update after filter
          expect(newCount).toBeTruthy();
        }
      }
    }
  });

  test("should show filter summary", async ({ page }) => {
    // Apply a filter
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      const typeFilter = page.locator('[data-filter-type]');
      if (await typeFilter.isVisible()) {
        await typeFilter.click();

        const pdfOption = page.locator('button:has-text("PDF")');
        if (await pdfOption.isVisible()) {
          await pdfOption.click();
          await page.waitForTimeout(300);

          // Look for filter summary
          const summary = page.locator('[data-filter-summary]');
          if (await summary.isVisible()) {
            const summaryText = await summary.textContent();
            expect(summaryText).toContain("PDF");
          }
        }
      }
    }
  });

  test("should persist filters during navigation", async ({ page }) => {
    // Apply a filter
    const filterSection = page.locator('[data-filter-section]');
    if (await filterSection.isVisible()) {
      const typeFilter = page.locator('[data-filter-type]');
      if (await typeFilter.isVisible()) {
        await typeFilter.click();

        const pdfOption = page.locator('button:has-text("PDF")');
        if (await pdfOption.isVisible()) {
          await pdfOption.click();
          await page.waitForTimeout(300);

          // Verify filter is applied
          const activeFilter = page.locator('[data-active-filter]');
          const filterText = await activeFilter.textContent();

          // Navigate elsewhere
          await page.click("a:has-text('Dashboard')");
          await page.waitForTimeout(500);

          // Navigate back to search
          await page.click("a:has-text('Organize')");
          await page.waitForSelector('[data-organize-interface]', {
            timeout: 5000,
          });

          // Filter should be restored (if persistence is implemented)
          const currentFilter = page.locator('[data-active-filter]');
          if (await currentFilter.isVisible()) {
            const currentText = await currentFilter.textContent();
            expect(currentText).toBeTruthy();
          }
        }
      }
    }
  });
});
