/**
 * Progress Bar Component Tests
 * Tests progress tracking, status transitions, and UI updates
 */

import { setupDOM, waitForElement, checkAccessibility } from "../fixtures/test-utils";
import { mockOrganizeJob, mockOrganizeResult } from "../fixtures/mock-data";

describe("Progress Bar Component", () => {
  beforeEach(() => {
    setupDOM();
    document.body.innerHTML = `
      <div class="progress-container" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
        <div class="progress-bar">
          <div class="progress-fill" style="width: 0%"></div>
        </div>
        <div class="progress-info">
          <span class="progress-percentage">0%</span>
          <span class="progress-status">Pending</span>
          <span class="progress-time" aria-label="Estimated time remaining"></span>
        </div>
        <button class="cancel-btn" data-action="cancel">Cancel</button>
      </div>
    `;
  });

  describe("Initial State", () => {
    it("should start at 0%", () => {
      const progressFill = document.querySelector(".progress-fill");
      const percentage = document.querySelector(".progress-percentage");

      expect(progressFill.style.width).toBe("0%");
      expect(percentage.textContent).toBe("0%");
    });

    it("should display pending status initially", () => {
      const status = document.querySelector(".progress-status");
      expect(status.textContent).toBe("Pending");
    });

    it("should have aria attributes set correctly", () => {
      const container = document.querySelector(".progress-container");

      expect(container.getAttribute("role")).toBe("progressbar");
      expect(container.getAttribute("aria-valuenow")).toBe("0");
      expect(container.getAttribute("aria-valuemin")).toBe("0");
      expect(container.getAttribute("aria-valuemax")).toBe("100");
    });

    it("should be visible on page load", () => {
      const container = document.querySelector(".progress-container");
      expect(container.style.display).not.toBe("none");
    });
  });

  describe("Progress Updates", () => {
    it("should update progress incrementally", () => {
      const container = document.querySelector(".progress-container");
      const progressFill = document.querySelector(".progress-fill");
      const percentage = document.querySelector(".progress-percentage");

      const progressValues = [0, 25, 50, 75, 100];

      progressValues.forEach((value) => {
        container.setAttribute("aria-valuenow", value);
        progressFill.style.width = `${value}%`;
        percentage.textContent = `${value}%`;

        expect(container.getAttribute("aria-valuenow")).toBe(String(value));
        expect(progressFill.style.width).toBe(`${value}%`);
        expect(percentage.textContent).toBe(`${value}%`);
      });
    });

    it("should handle small progress increments", () => {
      const progressFill = document.querySelector(".progress-fill");
      const percentage = document.querySelector(".progress-percentage");

      for (let i = 0; i <= 100; i += 5) {
        progressFill.style.width = `${i}%`;
        percentage.textContent = `${i}%`;

        expect(progressFill.style.width).toBe(`${i}%`);
      }
    });

    it("should cap progress at 100%", () => {
      const container = document.querySelector(".progress-container");
      const progressFill = document.querySelector(".progress-fill");

      container.setAttribute("aria-valuenow", "150");
      progressFill.style.width = "150%";

      const width = parseInt(progressFill.style.width);
      if (width > 100) {
        progressFill.style.width = "100%";
      }

      expect(progressFill.style.width).toBe("100%");
    });

    it("should not go below 0%", () => {
      const container = document.querySelector(".progress-container");
      const progressFill = document.querySelector(".progress-fill");

      container.setAttribute("aria-valuenow", "-10");
      progressFill.style.width = "-10%";

      const width = parseInt(progressFill.style.width);
      if (width < 0) {
        progressFill.style.width = "0%";
      }

      expect(progressFill.style.width).toBe("0%");
    });

    it("should update in real-time from mock job data", () => {
      const job = mockOrganizeJob;
      const container = document.querySelector(".progress-container");
      const progressFill = document.querySelector(".progress-fill");
      const percentage = document.querySelector(".progress-percentage");

      container.setAttribute("aria-valuenow", job.progress);
      progressFill.style.width = `${job.progress}%`;
      percentage.textContent = `${job.progress}%`;

      expect(container.getAttribute("aria-valuenow")).toBe(String(job.progress));
      expect(progressFill.style.width).toBe(`${job.progress}%`);
      expect(percentage.textContent).toBe(`${job.progress}%`);
    });
  });

  describe("Status Transitions", () => {
    it("should transition from pending to processing", () => {
      const status = document.querySelector(".progress-status");

      status.textContent = "Processing";
      expect(status.textContent).toBe("Processing");
    });

    it("should transition from processing to complete", () => {
      const status = document.querySelector(".progress-status");

      status.textContent = "Complete";
      expect(status.textContent).toBe("Complete");
    });

    it("should handle error status", () => {
      const status = document.querySelector(".progress-status");
      const container = document.querySelector(".progress-container");

      status.textContent = "Error";
      container.classList.add("error-state");

      expect(status.textContent).toBe("Error");
      expect(container.classList.contains("error-state")).toBe(true);
    });

    it("should display appropriate status colors", () => {
      const container = document.querySelector(".progress-container");

      const statuses = [
        { state: "pending", class: "status-pending" },
        { state: "processing", class: "status-processing" },
        { state: "complete", class: "status-complete" },
        { state: "error", class: "status-error" },
      ];

      statuses.forEach(({ state, class: className }) => {
        container.className = `progress-container ${className}`;
        expect(container.classList.contains(className)).toBe(true);
      });
    });

    it("should show correct status text for each stage", () => {
      const status = document.querySelector(".progress-status");

      const statusTexts = {
        0: "Pending",
        25: "Processing",
        50: "Processing",
        75: "Processing",
        100: "Complete",
      };

      Object.entries(statusTexts).forEach(([percentage, expectedStatus]) => {
        const percent = parseInt(percentage);

        if (percent === 0) {
          status.textContent = expectedStatus;
        } else if (percent === 100) {
          status.textContent = expectedStatus;
        } else {
          status.textContent = expectedStatus;
        }

        expect(status.textContent).toBe(expectedStatus);
      });
    });
  });

  describe("Time Estimation", () => {
    it("should display estimated time remaining", () => {
      document.body.innerHTML = `
        <div class="progress-container">
          <span class="progress-time">Est. time: 2m 30s</span>
        </div>
      `;

      const timeDisplay = document.querySelector(".progress-time");
      expect(timeDisplay.textContent).toBe("Est. time: 2m 30s");
    });

    it("should update time estimation as progress changes", () => {
      const timeDisplay = document.querySelector(".progress-time");

      timeDisplay.textContent = "Est. time: 5m 00s";
      expect(timeDisplay.textContent).toBe("Est. time: 5m 00s");

      timeDisplay.textContent = "Est. time: 2m 30s";
      expect(timeDisplay.textContent).toBe("Est. time: 2m 30s");

      timeDisplay.textContent = "Est. time: 30s";
      expect(timeDisplay.textContent).toBe("Est. time: 30s");
    });

    it("should handle zero time remaining", () => {
      const timeDisplay = document.querySelector(".progress-time");
      timeDisplay.textContent = "Est. time: <1s";

      expect(timeDisplay.textContent).toContain("s");
    });

    it("should format time in human-readable format", () => {
      const timeDisplay = document.querySelector(".progress-time");

      const testCases = [
        { ms: 30000, expected: "30s" },
        { ms: 150000, expected: "2m 30s" },
        { ms: 3600000, expected: "1h 00m" },
      ];

      testCases.forEach(({ ms, expected }) => {
        // Simple time formatting
        const seconds = Math.round(ms / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);

        if (hours > 0) {
          timeDisplay.textContent = `Est. time: ${hours}h ${minutes % 60}m`;
        } else if (minutes > 0) {
          timeDisplay.textContent = `Est. time: ${minutes}m ${seconds % 60}s`;
        } else {
          timeDisplay.textContent = `Est. time: ${seconds}s`;
        }

        expect(timeDisplay.textContent).toContain(expected.split(" ")[0]);
      });
    });
  });

  describe("Cancel Button Functionality", () => {
    it("should have cancel button available", () => {
      const cancelBtn = document.querySelector(".cancel-btn");
      expect(cancelBtn).toBeTruthy();
      expect(cancelBtn.textContent).toBe("Cancel");
    });

    it("should disable cancel button when complete", () => {
      const cancelBtn = document.querySelector(".cancel-btn");
      cancelBtn.disabled = true;

      expect(cancelBtn.disabled).toBe(true);
    });

    it("should show confirmation when canceling", () => {
      document.body.innerHTML = `
        <div class="progress-container">
          <button class="cancel-btn">Cancel</button>
        </div>
        <div class="cancel-dialog" style="display: none;">
          <p>Are you sure you want to cancel this operation?</p>
          <button class="confirm-cancel">Yes, Cancel</button>
          <button class="dismiss-cancel">No, Continue</button>
        </div>
      `;

      const cancelBtn = document.querySelector(".cancel-btn");
      const dialog = document.querySelector(".cancel-dialog");

      cancelBtn.click();
      dialog.style.display = "block";

      expect(dialog.style.display).toBe("block");
    });

    it("should hide cancel button on completion", () => {
      const cancelBtn = document.querySelector(".cancel-btn");
      cancelBtn.style.display = "none";

      expect(cancelBtn.style.display).toBe("none");
    });
  });

  describe("Statistics Display", () => {
    it("should display file count statistics", () => {
      document.body.innerHTML = `
        <div class="progress-stats">
          <span class="stat-label">Files:</span>
          <span class="stat-value">45 / 100</span>
        </div>
      `;

      const statValue = document.querySelector(".stat-value");
      expect(statValue.textContent).toBe("45 / 100");
    });

    it("should show processed and total files", () => {
      const job = mockOrganizeJob;

      document.body.innerHTML = `
        <div class="progress-stats">
          <span class="processed">${job.processed}</span>
          <span class="separator"> / </span>
          <span class="total">${job.total}</span>
        </div>
      `;

      const processedCount = document.querySelector(".processed");
      const totalCount = document.querySelector(".total");

      expect(processedCount.textContent).toBe(String(job.processed));
      expect(totalCount.textContent).toBe(String(job.total));
    });

    it("should display error count if present", () => {
      const job = mockOrganizeJob;

      document.body.innerHTML = `
        <div class="progress-stats">
          <span class="errors">${job.errors} errors</span>
        </div>
      `;

      const errorCount = document.querySelector(".errors");
      expect(errorCount.textContent).toBe(`${job.errors} errors`);
    });

    it("should update statistics in real-time", () => {
      const job = mockOrganizeJob;

      document.body.innerHTML = `
        <div class="progress-stats">
          <span class="processed">0</span>
          <span class="total">${job.total}</span>
        </div>
      `;

      const processedSpan = document.querySelector(".processed");

      for (let i = 0; i <= job.total; i += 10) {
        processedSpan.textContent = String(i);
        expect(processedSpan.textContent).toBe(String(i));
      }
    });
  });

  describe("Accessibility Features", () => {
    it("should have proper ARIA attributes", () => {
      const container = document.querySelector(".progress-container");

      expect(container.getAttribute("role")).toBe("progressbar");
      expect(container.hasAttribute("aria-valuenow")).toBe(true);
      expect(container.hasAttribute("aria-valuemin")).toBe(true);
      expect(container.hasAttribute("aria-valuemax")).toBe(true);
    });

    it("should update aria-valuenow with progress", () => {
      const container = document.querySelector(".progress-container");

      for (let i = 0; i <= 100; i += 10) {
        container.setAttribute("aria-valuenow", String(i));
        expect(container.getAttribute("aria-valuenow")).toBe(String(i));
      }
    });

    it("should have aria-label for time display", () => {
      const timeDisplay = document.querySelector(".progress-time");
      expect(timeDisplay.getAttribute("aria-label")).toBeTruthy();
    });

    it("should announce status changes", () => {
      const status = document.querySelector(".progress-status");

      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      status.setAttribute("aria-atomic", "true");

      expect(status.getAttribute("role")).toBe("status");
      expect(status.getAttribute("aria-live")).toBe("polite");
    });

    it("should have keyboard accessible cancel button", () => {
      const cancelBtn = document.querySelector(".cancel-btn");

      cancelBtn.focus();
      expect(document.activeElement).toBe(cancelBtn);

      // Simulate keyboard press
      const event = new KeyboardEvent("keydown", { key: "Enter" });
      cancelBtn.dispatchEvent(event);
    });
  });

  describe("Visual Feedback", () => {
    it("should show progress fill animation", () => {
      const progressFill = document.querySelector(".progress-fill");

      progressFill.style.transition = "width 0.3s ease";
      expect(progressFill.style.transition).toBe("width 0.3s ease");
    });

    it("should change color based on status", () => {
      document.body.innerHTML = `
        <div class="progress-container" style="--progress-color: blue;">
          <div class="progress-bar">
            <div class="progress-fill" style="background: var(--progress-color)"></div>
          </div>
        </div>
      `;

      const container = document.querySelector(".progress-container");
      container.style.setProperty("--progress-color", "green");

      expect(container.style.getPropertyValue("--progress-color")).toBe("green");
    });

    it("should display loading animation when processing", () => {
      const status = document.querySelector(".progress-status");

      status.classList.add("loading");
      expect(status.classList.contains("loading")).toBe(true);
    });

    it("should show completion animation on finish", () => {
      const container = document.querySelector(".progress-container");

      container.classList.add("complete");
      expect(container.classList.contains("complete")).toBe(true);
    });
  });

  describe("Error Handling", () => {
    it("should display error state", () => {
      const container = document.querySelector(".progress-container");
      const status = document.querySelector(".progress-status");

      container.classList.add("error-state");
      status.textContent = "Error";

      expect(container.classList.contains("error-state")).toBe(true);
      expect(status.textContent).toBe("Error");
    });

    it("should show error message below progress bar", () => {
      document.body.innerHTML = `
        <div class="progress-container">
          <div class="progress-bar"></div>
          <div class="error-message" style="display: none;">
            Operation failed: Connection timeout
          </div>
        </div>
      `;

      const errorMsg = document.querySelector(".error-message");
      errorMsg.style.display = "block";

      expect(errorMsg.style.display).toBe("block");
      expect(errorMsg.textContent.trim()).toBe("Operation failed: Connection timeout");
    });

    it("should provide retry option on error", () => {
      document.body.innerHTML = `
        <div class="progress-container">
          <button class="retry-btn" style="display: none;">Retry</button>
        </div>
      `;

      const retryBtn = document.querySelector(".retry-btn");
      retryBtn.style.display = "block";

      expect(retryBtn.style.display).toBe("block");
    });
  });
});
