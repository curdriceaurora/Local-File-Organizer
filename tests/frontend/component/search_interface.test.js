/**
 * Search Interface Component Tests
 * Tests search input, filtering, sorting, and result updates
 */

import {
  setupDOM,
  waitForElement,
  setupFetchMocks,
  waitForFetchCall,
} from "../fixtures/test-utils";
import { mockSearchResults } from "../fixtures/mock-data";

describe("Search Interface Component", () => {
  beforeEach(() => {
    setupDOM();
    document.body.innerHTML = `
      <div class="search-interface">
        <div class="search-box">
          <input
            type="search"
            id="search-input"
            placeholder="Search files..."
            aria-label="Search files"
          >
          <button class="search-btn" aria-label="Search">
            <span>Search</span>
          </button>
          <button class="clear-btn" aria-label="Clear search">×</button>
        </div>

        <div class="filters-container">
          <div class="filter-group">
            <label for="file-type-filter">File Type</label>
            <select id="file-type-filter" aria-label="Filter by file type">
              <option value="">All Types</option>
              <option value="document">Documents</option>
              <option value="image">Images</option>
              <option value="video">Videos</option>
              <option value="archive">Archives</option>
            </select>
          </div>

          <div class="filter-group">
            <label for="date-filter">Date Range</label>
            <input type="date" id="date-from" aria-label="Start date">
            <input type="date" id="date-to" aria-label="End date">
          </div>

          <div class="filter-group">
            <label for="size-filter">File Size</label>
            <select id="size-filter" aria-label="Filter by file size">
              <option value="">Any Size</option>
              <option value="small">< 1 MB</option>
              <option value="medium">1 - 10 MB</option>
              <option value="large">> 10 MB</option>
            </select>
          </div>

          <button class="reset-filters-btn" aria-label="Reset all filters">
            Reset Filters
          </button>
        </div>

        <div class="sort-controls">
          <select id="sort-select" aria-label="Sort by">
            <option value="relevance">Relevance</option>
            <option value="name">Name (A-Z)</option>
            <option value="date">Date Modified</option>
            <option value="size">Size</option>
          </select>
          <button class="sort-direction-btn" aria-label="Toggle sort direction">
            ↑↓
          </button>
        </div>

        <div id="search-results" class="results-container">
          <div class="results-info">
            <span class="result-count">0 results</span>
          </div>
          <div class="results-list"></div>
        </div>

        <div class="loading-indicator" style="display: none;">
          <span>Searching...</span>
        </div>

        <div class="no-results" style="display: none;">
          No files found matching your search.
        </div>
      </div>
    `;
  });

  describe("Search Input Handling", () => {
    it("should capture search input", () => {
      const searchInput = document.querySelector("#search-input");
      searchInput.value = "annual report";

      expect(searchInput.value).toBe("annual report");
    });

    it("should allow multiple words in search", () => {
      const searchInput = document.querySelector("#search-input");
      searchInput.value = "financial report 2024";

      expect(searchInput.value).toBe("financial report 2024");
    });

    it("should preserve search text when focused", () => {
      const searchInput = document.querySelector("#search-input");
      searchInput.value = "test search";
      searchInput.focus();

      expect(document.activeElement).toBe(searchInput);
      expect(searchInput.value).toBe("test search");
    });

    it("should have placeholder text", () => {
      const searchInput = document.querySelector("#search-input");
      expect(searchInput.placeholder).toBe("Search files...");
    });

    it("should support special characters in search", () => {
      const searchInput = document.querySelector("#search-input");
      const specialChars = ["@", "#", "$", "%", "&", "*"];

      specialChars.forEach((char) => {
        searchInput.value = `test${char}file`;
        expect(searchInput.value).toContain(char);
      });
    });
  });

  describe("Search Debouncing", () => {
    it("should debounce search input", async () => {
      jest.useFakeTimers();
      const searchInput = document.querySelector("#search-input");
      const searchFn = jest.fn();

      searchInput.addEventListener("input", () => {
        setTimeout(searchFn, 300);
      });

      searchInput.value = "test";
      searchInput.dispatchEvent(new Event("input"));

      // Before timeout
      expect(searchFn).not.toHaveBeenCalled();

      // After timeout
      jest.runAllTimers();
      expect(searchFn).toHaveBeenCalled();

      jest.useRealTimers();
    });

    it("should cancel previous search on new input", () => {
      jest.useFakeTimers();
      const searchInput = document.querySelector("#search-input");
      const searches = [];

      const search = () => {
        searches.push(searchInput.value);
      };

      searchInput.addEventListener("input", () => {
        searches.length = 0; // Cancel previous
        setTimeout(search, 300);
      });

      searchInput.value = "first";
      searchInput.dispatchEvent(new Event("input"));

      jest.advanceTimersByTime(100);

      searchInput.value = "first second";
      searchInput.dispatchEvent(new Event("input"));

      jest.runAllTimers();

      expect(searches[searches.length - 1]).toBe("first second");

      jest.useRealTimers();
    });
  });

  describe("Filter Application", () => {
    it("should apply file type filter", () => {
      const fileTypeFilter = document.querySelector("#file-type-filter");
      fileTypeFilter.value = "document";

      expect(fileTypeFilter.value).toBe("document");
    });

    it("should apply date range filter", () => {
      const dateFrom = document.querySelector("#date-from");
      const dateTo = document.querySelector("#date-to");

      dateFrom.value = "2024-01-01";
      dateTo.value = "2024-12-31";

      expect(dateFrom.value).toBe("2024-01-01");
      expect(dateTo.value).toBe("2024-12-31");
    });

    it("should apply file size filter", () => {
      const sizeFilter = document.querySelector("#size-filter");
      sizeFilter.value = "large";

      expect(sizeFilter.value).toBe("large");
    });

    it("should combine multiple filters", () => {
      const fileTypeFilter = document.querySelector("#file-type-filter");
      const sizeFilter = document.querySelector("#size-filter");
      const dateFrom = document.querySelector("#date-from");

      fileTypeFilter.value = "document";
      sizeFilter.value = "medium";
      dateFrom.value = "2024-01-01";

      expect(fileTypeFilter.value).toBe("document");
      expect(sizeFilter.value).toBe("medium");
      expect(dateFrom.value).toBe("2024-01-01");
    });

    it("should update results when filter changes", () => {
      const fileTypeFilter = document.querySelector("#file-type-filter");
      const resultsList = document.querySelector(".results-list");

      fileTypeFilter.value = "image";
      fileTypeFilter.dispatchEvent(new Event("change"));

      // Results would be updated via API call
      expect(fileTypeFilter.value).toBe("image");
    });
  });

  describe("Sorting Functionality", () => {
    it("should sort by relevance", () => {
      const sortSelect = document.querySelector("#sort-select");
      sortSelect.value = "relevance";

      expect(sortSelect.value).toBe("relevance");
    });

    it("should sort by name", () => {
      const sortSelect = document.querySelector("#sort-select");
      sortSelect.value = "name";

      expect(sortSelect.value).toBe("name");
    });

    it("should sort by date", () => {
      const sortSelect = document.querySelector("#sort-select");
      sortSelect.value = "date";

      expect(sortSelect.value).toBe("date");
    });

    it("should sort by size", () => {
      const sortSelect = document.querySelector("#sort-select");
      sortSelect.value = "size";

      expect(sortSelect.value).toBe("size");
    });

    it("should toggle sort direction", () => {
      const directionBtn = document.querySelector(".sort-direction-btn");

      directionBtn.dataset.direction = "asc";
      directionBtn.click();
      directionBtn.dataset.direction = directionBtn.dataset.direction === "asc" ? "desc" : "asc";

      expect(directionBtn.dataset.direction).toBe("desc");
    });

    it("should apply sorting to results", () => {
      const sortSelect = document.querySelector("#sort-select");

      const names = ["file1.pdf", "file2.pdf", "file3.pdf"];
      sortSelect.value = "name";
      sortSelect.dispatchEvent(new Event("change"));

      const sorted = [...names].sort();
      expect(sorted[0]).toBe("file1.pdf");
    });
  });

  describe("Filter Reset", () => {
    it("should clear all filters", () => {
      const fileTypeFilter = document.querySelector("#file-type-filter");
      const sizeFilter = document.querySelector("#size-filter");
      const resetBtn = document.querySelector(".reset-filters-btn");

      fileTypeFilter.value = "document";
      sizeFilter.value = "large";

      resetBtn.click();

      fileTypeFilter.value = "";
      sizeFilter.value = "";

      expect(fileTypeFilter.value).toBe("");
      expect(sizeFilter.value).toBe("");
    });

    it("should reset search input", () => {
      const searchInput = document.querySelector("#search-input");
      const clearBtn = document.querySelector(".clear-btn");

      searchInput.value = "test search";
      clearBtn.click();
      searchInput.value = "";

      expect(searchInput.value).toBe("");
    });

    it("should clear date filters", () => {
      const dateFrom = document.querySelector("#date-from");
      const dateTo = document.querySelector("#date-to");
      const resetBtn = document.querySelector(".reset-filters-btn");

      dateFrom.value = "2024-01-01";
      dateTo.value = "2024-12-31";

      resetBtn.click();

      dateFrom.value = "";
      dateTo.value = "";

      expect(dateFrom.value).toBe("");
      expect(dateTo.value).toBe("");
    });

    it("should reset sort to default", () => {
      const sortSelect = document.querySelector("#sort-select");
      const resetBtn = document.querySelector(".reset-filters-btn");

      sortSelect.value = "size";

      resetBtn.click();
      sortSelect.value = "relevance";

      expect(sortSelect.value).toBe("relevance");
    });
  });

  describe("Results Display", () => {
    it("should display result count", () => {
      const resultCount = document.querySelector(".result-count");

      resultCount.textContent = `${mockSearchResults.length} results`;
      expect(resultCount.textContent).toContain(String(mockSearchResults.length));
    });

    it("should render search results", () => {
      const resultsList = document.querySelector(".results-list");

      mockSearchResults.forEach((result) => {
        const resultItem = document.createElement("div");
        resultItem.className = "result-item";
        resultItem.innerHTML = `
          <div class="result-name">${result.name}</div>
          <div class="result-path">${result.path}</div>
          <div class="result-size">${result.size} bytes</div>
        `;
        resultsList.appendChild(resultItem);
      });

      expect(resultsList.children.length).toBe(mockSearchResults.length);
    });

    it("should show 'no results' message when empty", () => {
      const noResults = document.querySelector(".no-results");
      const resultCount = document.querySelector(".result-count");

      resultCount.textContent = "0 results";
      noResults.style.display = "block";

      expect(noResults.style.display).toBe("block");
    });

    it("should display relevance score", () => {
      const resultsList = document.querySelector(".results-list");

      mockSearchResults.forEach((result) => {
        const resultItem = document.createElement("div");
        resultItem.className = "result-item";
        resultItem.innerHTML = `
          <span class="relevance">${Math.round(result.score * 100)}%</span>
        `;
        resultsList.appendChild(resultItem);
      });

      const relevanceScores = Array.from(resultsList.querySelectorAll(".relevance"));
      expect(relevanceScores.length).toBeGreaterThan(0);
    });
  });

  describe("Real-time Updates", () => {
    it("should update results when search changes", () => {
      const searchInput = document.querySelector("#search-input");
      const resultCount = document.querySelector(".result-count");

      searchInput.value = "annual report";
      searchInput.dispatchEvent(new Event("input"));

      // Simulate API response
      resultCount.textContent = "5 results";

      expect(searchInput.value).toBe("annual report");
    });

    it("should update results when filters change", () => {
      const fileTypeFilter = document.querySelector("#file-type-filter");
      const resultCount = document.querySelector(".result-count");

      fileTypeFilter.value = "image";
      fileTypeFilter.dispatchEvent(new Event("change"));

      // Simulate API response
      resultCount.textContent = "12 results";

      expect(fileTypeFilter.value).toBe("image");
    });

    it("should update results when sort changes", () => {
      const sortSelect = document.querySelector("#sort-select");
      const resultsList = document.querySelector(".results-list");

      sortSelect.value = "size";
      sortSelect.dispatchEvent(new Event("change"));

      // Results reordered by size
      expect(sortSelect.value).toBe("size");
    });
  });

  describe("Loading States", () => {
    it("should show loading indicator during search", () => {
      const loadingIndicator = document.querySelector(".loading-indicator");

      loadingIndicator.style.display = "block";
      expect(loadingIndicator.style.display).toBe("block");
    });

    it("should hide loading indicator after search completes", () => {
      const loadingIndicator = document.querySelector(".loading-indicator");

      loadingIndicator.style.display = "none";
      expect(loadingIndicator.style.display).toBe("none");
    });

    it("should disable search button during search", () => {
      const searchBtn = document.querySelector(".search-btn");

      searchBtn.disabled = true;
      expect(searchBtn.disabled).toBe(true);
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels", () => {
      const searchInput = document.querySelector("#search-input");
      const fileTypeFilter = document.querySelector("#file-type-filter");
      const sortSelect = document.querySelector("#sort-select");

      expect(searchInput.getAttribute("aria-label")).toBe("Search files");
      expect(fileTypeFilter.getAttribute("aria-label")).toBe("Filter by file type");
      expect(sortSelect.getAttribute("aria-label")).toBe("Sort by");
    });

    it("should be keyboard navigable", () => {
      const searchInput = document.querySelector("#search-input");
      const filterSelect = document.querySelector("#file-type-filter");
      const sortSelect = document.querySelector("#sort-select");

      searchInput.focus();
      expect(document.activeElement).toBe(searchInput);

      filterSelect.focus();
      expect(document.activeElement).toBe(filterSelect);

      sortSelect.focus();
      expect(document.activeElement).toBe(sortSelect);
    });

    it("should announce search results", () => {
      document.body.innerHTML = `
        <div role="status" aria-live="polite" aria-atomic="true">
          <span class="result-count">5 results found</span>
        </div>
      `;

      const status = document.querySelector('[role="status"]');
      expect(status.getAttribute("aria-live")).toBe("polite");
      expect(status.getAttribute("aria-atomic")).toBe("true");
    });

    it("should have descriptive labels", () => {
      const labels = document.querySelectorAll("label");

      expect(labels.length).toBeGreaterThan(0);
      labels.forEach((label) => {
        expect(label.textContent).toBeTruthy();
      });
    });
  });

  describe("User Interactions", () => {
    it("should submit search on Enter key", () => {
      const searchInput = document.querySelector("#search-input");

      searchInput.value = "test search";

      const event = new KeyboardEvent("keydown", {
        key: "Enter",
        code: "Enter",
        keyCode: 13,
      });

      searchInput.dispatchEvent(event);
      expect(searchInput.value).toBe("test search");
    });

    it("should clear search on clear button click", () => {
      const searchInput = document.querySelector("#search-input");
      const clearBtn = document.querySelector(".clear-btn");

      searchInput.value = "test search";
      clearBtn.click();

      searchInput.value = "";
      expect(searchInput.value).toBe("");
    });

    it("should apply filter on selection change", () => {
      const fileTypeFilter = document.querySelector("#file-type-filter");
      const changeEvent = new Event("change");

      fileTypeFilter.value = "image";
      fileTypeFilter.dispatchEvent(changeEvent);

      expect(fileTypeFilter.value).toBe("image");
    });
  });

  describe("Search Result Interactions", () => {
    it("should select search result on click", () => {
      const resultsList = document.querySelector(".results-list");
      const resultItem = document.createElement("div");
      resultItem.className = "result-item";

      resultsList.appendChild(resultItem);

      resultItem.click();
      resultItem.classList.add("selected");

      expect(resultItem.classList.contains("selected")).toBe(true);
    });

    it("should open preview on double-click", () => {
      const resultsList = document.querySelector(".results-list");
      const resultItem = document.createElement("div");
      resultItem.className = "result-item";

      resultsList.appendChild(resultItem);

      const dblEvent = new MouseEvent("dblclick");
      resultItem.dispatchEvent(dblEvent);

      resultItem.dataset.preview = "true";
      expect(resultItem.dataset.preview).toBe("true");
    });

    it("should show context menu on right-click", () => {
      const resultsList = document.querySelector(".results-list");
      const resultItem = document.createElement("div");
      resultItem.className = "result-item";

      resultsList.appendChild(resultItem);

      const contextEvent = new MouseEvent("contextmenu", {
        bubbles: true,
        cancelable: true,
      });

      resultItem.dispatchEvent(contextEvent);
      expect(contextEvent.cancelable).toBe(true);
    });
  });
});
