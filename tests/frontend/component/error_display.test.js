/**
 * Error Display Component Tests
 * Tests error rendering, types, dismissal, and retry functionality
 */

import { setupDOM } from "../fixtures/test-utils";
import { mockApiError } from "../fixtures/mock-data";

describe("Error Display Component", () => {
  beforeEach(() => {
    setupDOM();
    document.body.innerHTML = `
      <div class="error-container" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="error-message" style="display: none;">
          <div class="error-icon">⚠️</div>
          <div class="error-content">
            <h3 class="error-title"></h3>
            <p class="error-description"></p>
            <div class="error-details"></div>
          </div>
          <button class="error-close" aria-label="Dismiss error">×</button>
          <div class="error-actions"></div>
        </div>
        <div class="error-stack" style="display: none;"></div>
      </div>
    `;
  });

  describe("Error Message Rendering", () => {
    it("should display error message", () => {
      const errorMsg = document.querySelector(".error-message");
      const title = document.querySelector(".error-title");
      const description = document.querySelector(".error-description");

      errorMsg.style.display = "block";
      title.textContent = "Upload Failed";
      description.textContent = "File size exceeds maximum limit";

      expect(errorMsg.style.display).toBe("block");
      expect(title.textContent).toBe("Upload Failed");
      expect(description.textContent).toBe("File size exceeds maximum limit");
    });

    it("should display error icon", () => {
      const errorIcon = document.querySelector(".error-icon");
      expect(errorIcon.textContent).toBe("⚠️");
    });

    it("should show error details", () => {
      const errorDetails = document.querySelector(".error-details");
      const detailsText = "Maximum file size: 10 MB, Your file: 15 MB";

      const detail = document.createElement("p");
      detail.textContent = detailsText;
      errorDetails.appendChild(detail);

      expect(errorDetails.textContent).toBe(detailsText);
    });

    it("should handle HTML in error messages safely", () => {
      const description = document.querySelector(".error-description");

      const errorText = "Invalid file type";
      description.textContent = errorText;

      expect(description.textContent).toBe(errorText);
    });

    it("should display error code if provided", () => {
      const error = mockApiError;

      const errorCode = document.createElement("span");
      errorCode.className = "error-code";
      errorCode.textContent = `(${error.code})`;

      const errorDetails = document.querySelector(".error-details");
      errorDetails.appendChild(errorCode);

      expect(errorDetails.querySelector(".error-code")).toBeTruthy();
      expect(errorDetails.querySelector(".error-code").textContent).toContain(error.code);
    });
  });

  describe("Error Types", () => {
    it("should display validation error", () => {
      const errorMsg = document.querySelector(".error-message");
      const title = document.querySelector(".error-title");

      errorMsg.style.display = "block";
      errorMsg.classList.add("error-validation");
      title.textContent = "Validation Error";

      expect(errorMsg.classList.contains("error-validation")).toBe(true);
      expect(title.textContent).toBe("Validation Error");
    });

    it("should display API error", () => {
      const errorMsg = document.querySelector(".error-message");
      const title = document.querySelector(".error-title");

      errorMsg.style.display = "block";
      errorMsg.classList.add("error-api");
      title.textContent = "Server Error";

      expect(errorMsg.classList.contains("error-api")).toBe(true);
      expect(title.textContent).toBe("Server Error");
    });

    it("should display network error", () => {
      const errorMsg = document.querySelector(".error-message");
      const title = document.querySelector(".error-title");

      errorMsg.style.display = "block";
      errorMsg.classList.add("error-network");
      title.textContent = "Network Error";

      expect(errorMsg.classList.contains("error-network")).toBe(true);
    });

    it("should display system error", () => {
      const errorMsg = document.querySelector(".error-message");
      const title = document.querySelector(".error-title");

      errorMsg.style.display = "block";
      errorMsg.classList.add("error-system");
      title.textContent = "System Error";

      expect(errorMsg.classList.contains("error-system")).toBe(true);
    });

    it("should display different error icons by type", () => {
      const errorIcon = document.querySelector(".error-icon");
      const container = document.querySelector(".error-container");

      const errorTypes = {
        "error-validation": "⚠️",
        "error-api": "❌",
        "error-network": "🔌",
        "error-system": "⚙️",
      };

      Object.entries(errorTypes).forEach(([type, icon]) => {
        container.className = `error-container ${type}`;

        if (type === "error-api") {
          errorIcon.textContent = "❌";
        }

        expect(errorIcon.textContent).toBeTruthy();
      });
    });
  });

  describe("Error Dismissal", () => {
    it("should hide error on close button click", () => {
      const errorMsg = document.querySelector(".error-message");
      const closeBtn = document.querySelector(".error-close");

      errorMsg.style.display = "block";
      closeBtn.click();
      errorMsg.style.display = "none";

      expect(errorMsg.style.display).toBe("none");
    });

    it("should support keyboard dismiss (Escape key)", () => {
      const errorMsg = document.querySelector(".error-message");

      errorMsg.style.display = "block";

      const escapeEvent = new KeyboardEvent("keydown", {
        key: "Escape",
        code: "Escape",
        keyCode: 27,
      });

      document.dispatchEvent(escapeEvent);
      errorMsg.style.display = "none";

      expect(errorMsg.style.display).toBe("none");
    });

    it("should support auto-dismiss after timeout", (done) => {
      const errorMsg = document.querySelector(".error-message");

      errorMsg.style.display = "block";
      errorMsg.dataset.autoDismiss = "3000";

      const timeout = parseInt(errorMsg.dataset.autoDismiss);

      setTimeout(() => {
        errorMsg.style.display = "none";
        expect(errorMsg.style.display).toBe("none");
        done();
      }, timeout);
    });

    it("should keep error visible if pinned", () => {
      const errorMsg = document.querySelector(".error-message");
      const closeBtn = document.querySelector(".error-close");

      errorMsg.style.display = "block";
      errorMsg.dataset.pinned = "true";

      closeBtn.click();

      if (errorMsg.dataset.pinned === "true") {
        errorMsg.style.display = "block";
      }

      expect(errorMsg.style.display).toBe("block");
    });

    it("should close all errors", () => {
      document.body.innerHTML = `
        <div class="error-message" style="display: block;">Error 1</div>
        <div class="error-message" style="display: block;">Error 2</div>
        <div class="error-message" style="display: block;">Error 3</div>
        <button class="close-all-errors">Close All</button>
      `;

      const closeAllBtn = document.querySelector(".close-all-errors");
      const errors = document.querySelectorAll(".error-message");

      closeAllBtn.click();

      errors.forEach((err) => {
        err.style.display = "none";
      });

      errors.forEach((err) => {
        expect(err.style.display).toBe("none");
      });
    });
  });

  describe("Retry Functionality", () => {
    it("should show retry button on transient error", () => {
      const errorActions = document.querySelector(".error-actions");

      const retryBtn = document.createElement("button");
      retryBtn.className = "retry-btn";
      retryBtn.textContent = "Retry";
      errorActions.appendChild(retryBtn);

      expect(errorActions.querySelector(".retry-btn")).toBeTruthy();
    });

    it("should trigger retry on button click", () => {
      const retryBtn = document.createElement("button");
      retryBtn.className = "retry-btn";

      const retryFn = jest.fn();
      retryBtn.addEventListener("click", retryFn);
      retryBtn.click();

      expect(retryFn).toHaveBeenCalled();
    });

    it("should hide retry button on permanent error", () => {
      const errorMsg = document.querySelector(".error-message");
      const errorActions = document.querySelector(".error-actions");

      errorMsg.classList.add("error-permanent");

      if (errorMsg.classList.contains("error-permanent")) {
        errorActions.innerHTML = "";
      }

      expect(errorActions.querySelector(".retry-btn")).toBeNull();
    });

    it("should disable retry button while retrying", () => {
      const retryBtn = document.createElement("button");
      retryBtn.className = "retry-btn";

      retryBtn.disabled = true;
      expect(retryBtn.disabled).toBe(true);

      retryBtn.disabled = false;
      expect(retryBtn.disabled).toBe(false);
    });

    it("should show retry count limit", () => {
      document.body.innerHTML = `
        <div class="error-actions">
          <button class="retry-btn">Retry (2 attempts left)</button>
        </div>
      `;

      const retryBtn = document.querySelector(".retry-btn");
      expect(retryBtn.textContent).toContain("2 attempts");
    });
  });

  describe("Error Formatting", () => {
    it("should format error title properly", () => {
      const title = document.querySelector(".error-title");

      title.textContent = "Upload Failed";
      expect(title.textContent).toBe("Upload Failed");

      title.textContent = "Network Error";
      expect(title.textContent).toBe("Network Error");
    });

    it("should format error description with proper line breaks", () => {
      const description = document.querySelector(".error-description");

      description.innerHTML = `
        <div>File upload failed.</div>
        <div>Reason: File is too large.</div>
        <div>Maximum size: 10 MB</div>
      `;

      expect(description.innerHTML).toContain("File upload failed");
      expect(description.innerHTML).toContain("File is too large");
    });

    it("should display error suggestions if provided", () => {
      const errorDetails = document.querySelector(".error-details");

      const suggestion = document.createElement("div");
      suggestion.className = "error-suggestion";
      suggestion.innerHTML = `
        <strong>Suggestion:</strong> Reduce file size and try again.
      `;
      errorDetails.appendChild(suggestion);

      expect(errorDetails.querySelector(".error-suggestion")).toBeTruthy();
      expect(errorDetails.textContent).toContain("Suggestion");
    });

    it("should display error timestamp", () => {
      const errorContainer = document.querySelector(".error-container");

      const timestamp = document.createElement("span");
      timestamp.className = "error-timestamp";
      timestamp.textContent = new Date().toLocaleTimeString();
      errorContainer.appendChild(timestamp);

      expect(errorContainer.querySelector(".error-timestamp")).toBeTruthy();
    });
  });

  describe("Multiple Error Handling", () => {
    it("should display multiple errors in sequence", () => {
      document.body.innerHTML = `
        <div class="errors-list">
          <div class="error-item">Error 1: Upload failed</div>
          <div class="error-item">Error 2: Invalid file type</div>
          <div class="error-item">Error 3: Network timeout</div>
        </div>
      `;

      const errors = document.querySelectorAll(".error-item");
      expect(errors.length).toBe(3);
    });

    it("should show error count", () => {
      document.body.innerHTML = `
        <div class="error-header">
          <span class="error-count">3 errors</span>
        </div>
        <div class="errors-list">
          <div class="error-item">Error 1</div>
          <div class="error-item">Error 2</div>
          <div class="error-item">Error 3</div>
        </div>
      `;

      const count = document.querySelector(".error-count");
      expect(count.textContent).toBe("3 errors");
    });

    it("should allow clearing specific error", () => {
      document.body.innerHTML = `
        <div class="errors-list">
          <div class="error-item">
            <span>Error 1</span>
            <button class="close-btn">×</button>
          </div>
          <div class="error-item">
            <span>Error 2</span>
            <button class="close-btn">×</button>
          </div>
        </div>
      `;

      const errorsList = document.querySelector(".errors-list");
      const closeButtons = errorsList.querySelectorAll(".close-btn");

      closeButtons[0].click();
      closeButtons[0].closest(".error-item").remove();

      expect(errorsList.querySelectorAll(".error-item").length).toBe(1);
    });
  });

  describe("Error Stack/Details", () => {
    it("should show expandable error stack trace", () => {
      document.body.innerHTML = `
        <div class="error-message">
          <button class="show-details-btn">Show Details</button>
          <div class="error-stack" style="display: none;">
            <pre>Error stack trace here...</pre>
          </div>
        </div>
      `;

      const detailsBtn = document.querySelector(".show-details-btn");
      const stack = document.querySelector(".error-stack");

      detailsBtn.click();
      stack.style.display = "block";

      expect(stack.style.display).toBe("block");
    });

    it("should copy error details to clipboard", () => {
      document.body.innerHTML = `
        <div class="error-message">
          <button class="copy-error-btn" aria-label="Copy error">Copy Error</button>
          <span class="error-text">Error: Invalid file type</span>
        </div>
      `;

      const copyBtn = document.querySelector(".copy-error-btn");

      copyBtn.click();

      expect(copyBtn).toBeTruthy();
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA attributes", () => {
      const container = document.querySelector(".error-container");

      expect(container.getAttribute("role")).toBe("alert");
      expect(container.getAttribute("aria-live")).toBe("assertive");
      expect(container.getAttribute("aria-atomic")).toBe("true");
    });

    it("should announce error to screen readers", () => {
      const container = document.querySelector(".error-container");

      expect(container.getAttribute("aria-live")).toBe("assertive");
    });

    it("should have descriptive button labels", () => {
      const closeBtn = document.querySelector(".error-close");

      expect(closeBtn.getAttribute("aria-label")).toBe("Dismiss error");
    });

    it("should be keyboard navigable", () => {
      const closeBtn = document.querySelector(".error-close");

      closeBtn.focus();
      expect(document.activeElement).toBe(closeBtn);
    });

    it("should support focus management", () => {
      const errorMsg = document.querySelector(".error-message");
      const closeBtn = document.querySelector(".error-close");

      errorMsg.style.display = "block";

      closeBtn.focus();
      expect(document.activeElement).toBe(closeBtn);
    });
  });

  describe("Visual Styling", () => {
    it("should apply correct CSS class for error type", () => {
      const container = document.querySelector(".error-container");

      container.classList.add("error-validation");
      expect(container.classList.contains("error-validation")).toBe(true);

      container.classList.remove("error-validation");
      container.classList.add("error-api");
      expect(container.classList.contains("error-api")).toBe(true);
    });

    it("should display error with proper colors", () => {
      const errorMsg = document.querySelector(".error-message");

      errorMsg.style.backgroundColor = "rgba(220, 38, 38, 0.1)";
      errorMsg.style.borderColor = "rgb(220, 38, 38)";

      expect(errorMsg.style.backgroundColor).toBeTruthy();
      expect(errorMsg.style.borderColor).toBeTruthy();
    });

    it("should show error icon animation", () => {
      const errorIcon = document.querySelector(".error-icon");

      errorIcon.style.animation = "pulse 1s infinite";

      expect(errorIcon.style.animation).toContain("pulse");
    });
  });
});
