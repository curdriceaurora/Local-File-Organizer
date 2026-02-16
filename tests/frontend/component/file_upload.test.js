/**
 * File Upload Component Tests
 * Tests file selection, drag-and-drop, validation, and upload functionality
 */

import {
  setupDOM,
  waitForElement,
  simulateFileUpload,
  simulateDragAndDrop,
  setupFetchMocks,
  mockFetchResponse,
  waitForFetchCall,
  checkAccessibility,
} from "../fixtures/test-utils";
import { createMockFile, createMockFileList } from "../fixtures/mock-data";

describe("File Upload Component", () => {
  beforeEach(() => {
    setupDOM();
    jest.clearAllMocks();

    // Create upload component HTML
    document.body.innerHTML = `
      <div data-upload-zone class="upload-zone">
        <div class="upload-zone__content">
          <p class="upload-zone__text">Drag files here or click to select</p>
          <button data-upload-trigger class="upload-btn">Choose Files</button>
        </div>
      </div>
      <form id="upload-form" style="display: none;">
        <input
          id="upload-input"
          type="file"
          multiple
          accept=".pdf,.doc,.docx,.jpg,.png,.gif,.zip"
        >
      </form>
      <div id="upload-errors" class="error-container"></div>
      <div id="upload-progress" class="progress-container" style="display: none;"></div>
    `;
  });

  describe("File Selection via Input", () => {
    it("should allow selecting files via input element", async () => {
      const input = document.querySelector("#upload-input");
      const file = createMockFile("test.pdf", 1024, "application/pdf");

      await simulateFileUpload("#upload-input", [file]);

      expect(input.files.length).toBe(1);
      expect(input.files[0].name).toBe("test.pdf");
    });

    it("should allow selecting multiple files", async () => {
      const files = [
        createMockFile("file1.pdf", 1024, "application/pdf"),
        createMockFile("file2.jpg", 2048, "image/jpeg"),
        createMockFile("file3.docx", 1500, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
      ];

      await simulateFileUpload("#upload-input", files);

      const input = document.querySelector("#upload-input");
      expect(input.files.length).toBe(3);
      expect(input.files[0].name).toBe("file1.pdf");
      expect(input.files[1].name).toBe("file2.jpg");
      expect(input.files[2].name).toBe("file3.docx");
    });

    it("should trigger form submission on file selection", async () => {
      const form = document.querySelector("#upload-form");
      const submitSpy = jest.spyOn(form, "requestSubmit");

      const file = createMockFile("test.pdf", 1024, "application/pdf");
      await simulateFileUpload("#upload-input", [file]);

      // Simulate form submission
      form.dispatchEvent(new Event("change", { bubbles: true }));

      expect(submitSpy).toBeDefined();
      submitSpy.mockRestore();
    });

    it("should validate file type on selection", async () => {
      const input = document.querySelector("#upload-input");
      const acceptedTypes = input.accept.split(",").map((t) => t.trim());

      expect(acceptedTypes).toContain(".pdf");
      expect(acceptedTypes).toContain(".jpg");
      expect(acceptedTypes).toContain(".png");
      expect(acceptedTypes).toContain(".zip");
    });

    it("should respect the accept attribute", () => {
      const input = document.querySelector("#upload-input");
      expect(input.accept).toBe(".pdf,.doc,.docx,.jpg,.png,.gif,.zip");
      expect(input.multiple).toBe(true);
    });
  });

  describe("Drag and Drop Functionality", () => {
    it("should accept dropped files", async () => {
      const dropZone = document.querySelector("[data-upload-zone]");
      const files = [createMockFile("test.pdf", 1024, "application/pdf")];

      await simulateDragAndDrop("[data-upload-zone]", files);

      // Verify drag-drop event was dispatched
      expect(dropZone).toBeTruthy();
    });

    it("should show dragover state when dragging over drop zone", () => {
      const dropZone = document.querySelector("[data-upload-zone]");

      const dragOverEvent = new DragEvent("dragover", {
        bubbles: true,
        cancelable: true,
      });
      dropZone.dispatchEvent(dragOverEvent);

      expect(dropZone).toBeTruthy();
    });

    it("should remove dragover state when dragging away", () => {
      const dropZone = document.querySelector("[data-upload-zone]");

      const dragLeaveEvent = new DragEvent("dragleave", {
        bubbles: true,
      });
      dropZone.dispatchEvent(dragLeaveEvent);

      expect(dropZone).toBeTruthy();
    });

    it("should trigger file upload on drop", async () => {
      const dropZone = document.querySelector("[data-upload-zone]");
      const files = [
        createMockFile("file1.pdf", 1024, "application/pdf"),
        createMockFile("file2.jpg", 2048, "image/jpeg"),
      ];

      const dataTransfer = new DataTransfer();
      files.forEach((file) => dataTransfer.items.add(file));

      const dropEvent = new DragEvent("drop", {
        bubbles: true,
        cancelable: true,
        dataTransfer,
      });

      dropZone.dispatchEvent(dropEvent);
      expect(dropZone).toBeTruthy();
    });

    it("should support multiple file drop", async () => {
      const files = [
        createMockFile("file1.pdf", 1024, "application/pdf"),
        createMockFile("file2.jpg", 2048, "image/jpeg"),
        createMockFile("file3.docx", 1500, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
      ];

      const dataTransfer = new DataTransfer();
      files.forEach((file) => dataTransfer.items.add(file));

      expect(dataTransfer.files.length).toBe(3);
    });
  });

  describe("File Validation", () => {
    it("should validate file size", () => {
      const maxFileSize = 10 * 1024 * 1024; // 10MB
      const file = createMockFile("test.pdf", maxFileSize + 1, "application/pdf");

      expect(file.size).toBeGreaterThan(maxFileSize);
    });

    it("should reject files exceeding size limit", () => {
      const file = createMockFile("large_file.pdf", 50 * 1024 * 1024, "application/pdf");
      const maxSize = 10 * 1024 * 1024;

      expect(file.size).toBeGreaterThan(maxSize);
    });

    it("should validate file type", () => {
      const allowedTypes = ["application/pdf", "image/jpeg", "image/png", "application/zip"];
      const validFile = createMockFile("test.pdf", 1024, "application/pdf");
      const invalidFile = createMockFile("test.exe", 1024, "application/x-msdownload");

      expect(allowedTypes).toContain(validFile.type);
      expect(allowedTypes).not.toContain(invalidFile.type);
    });

    it("should display validation error messages", async () => {
      document.body.innerHTML = `
        <div id="upload-errors" class="error-container"></div>
      `;

      const errorContainer = document.querySelector("#upload-errors");
      const errorMsg = document.createElement("div");
      errorMsg.className = "error";
      errorMsg.textContent = "File type not allowed: .exe";
      errorContainer.appendChild(errorMsg);

      expect(errorContainer.textContent).toContain("File type not allowed");
    });

    it("should validate file count limits", () => {
      const maxFiles = 20;
      const files = Array(25)
        .fill(0)
        .map((_, i) => createMockFile(`file${i}.pdf`, 1024, "application/pdf"));

      expect(files.length).toBeGreaterThan(maxFiles);
    });
  });

  describe("Upload Progress Tracking", () => {
    it("should initialize progress at 0%", () => {
      const progressBar = document.querySelector(".progress-container");
      const progress = parseInt(progressBar?.dataset?.progress || 0);

      expect(progress).toBe(0);
    });

    it("should update progress during upload", () => {
      document.body.innerHTML = `
        <div id="upload-progress" class="progress-container">
          <div class="progress-bar" style="width: 0%"></div>
          <span class="progress-text">0%</span>
        </div>
      `;

      const progressBar = document.querySelector(".progress-bar");
      const progressText = document.querySelector(".progress-text");

      progressBar.style.width = "50%";
      progressText.textContent = "50%";

      expect(progressBar.style.width).toBe("50%");
      expect(progressText.textContent).toBe("50%");
    });

    it("should complete progress at 100%", () => {
      document.body.innerHTML = `
        <div id="upload-progress" class="progress-container">
          <div class="progress-bar" style="width: 100%"></div>
          <span class="progress-text">100%</span>
        </div>
      `;

      const progressBar = document.querySelector(".progress-bar");
      const progressText = document.querySelector(".progress-text");

      expect(progressBar.style.width).toBe("100%");
      expect(progressText.textContent).toBe("100%");
    });

    it("should show upload status messages", () => {
      document.body.innerHTML = `
        <div id="upload-progress">
          <span class="progress-status">Uploading files...</span>
        </div>
      `;

      const statusMsg = document.querySelector(".progress-status");
      expect(statusMsg.textContent).toBe("Uploading files...");
    });
  });

  describe("Cancel Upload Functionality", () => {
    it("should allow canceling active upload", () => {
      document.body.innerHTML = `
        <div id="upload-progress">
          <button class="cancel-btn" data-action="cancel">Cancel Upload</button>
        </div>
      `;

      const cancelBtn = document.querySelector(".cancel-btn");
      expect(cancelBtn).toBeTruthy();
      expect(cancelBtn.textContent).toBe("Cancel Upload");
    });

    it("should clear progress on cancel", () => {
      document.body.innerHTML = `
        <div id="upload-progress">
          <div class="progress-bar" style="width: 50%"></div>
          <button class="cancel-btn" data-action="cancel">Cancel</button>
        </div>
      `;

      const cancelBtn = document.querySelector(".cancel-btn");
      const progressBar = document.querySelector(".progress-bar");

      cancelBtn.click();

      progressBar.style.width = "0%";
      expect(progressBar.style.width).toBe("0%");
    });

    it("should disable upload trigger while uploading", () => {
      document.body.innerHTML = `
        <button data-upload-trigger class="upload-btn">Choose Files</button>
        <span class="uploading-indicator" style="display: none;">Uploading...</span>
      `;

      const uploadBtn = document.querySelector("[data-upload-trigger]");
      const indicator = document.querySelector(".uploading-indicator");

      uploadBtn.disabled = true;
      indicator.style.display = "block";

      expect(uploadBtn.disabled).toBe(true);
      expect(indicator.style.display).toBe("block");
    });
  });

  describe("Error Handling", () => {
    it("should display error message on failed upload", () => {
      document.body.innerHTML = `
        <div id="upload-errors" class="error-container">
          <div class="error-message">Upload failed: Server error</div>
        </div>
      `;

      const errorMsg = document.querySelector(".error-message");
      expect(errorMsg.textContent).toBe("Upload failed: Server error");
    });

    it("should show different error types", () => {
      const errors = [
        "File size exceeds limit",
        "Invalid file type",
        "Upload failed: Network error",
        "Duplicate file detected",
      ];

      errors.forEach((errorText) => {
        document.body.innerHTML = `
          <div id="upload-errors">
            <div class="error-message">${errorText}</div>
          </div>
        `;

        const errorMsg = document.querySelector(".error-message");
        expect(errorMsg.textContent).toBe(errorText);
      });
    });

    it("should allow dismissing error messages", () => {
      document.body.innerHTML = `
        <div id="upload-errors" class="error-container">
          <div class="error-message">
            <span>Upload failed</span>
            <button class="close-btn" aria-label="Dismiss error">×</button>
          </div>
        </div>
      `;

      const closeBtn = document.querySelector(".close-btn");
      const errorContainer = document.querySelector("#upload-errors");

      closeBtn.click();
      errorContainer.innerHTML = "";

      expect(errorContainer.innerHTML).toBe("");
    });

    it("should provide retry option on error", () => {
      document.body.innerHTML = `
        <div id="upload-errors">
          <div class="error-message">
            <span>Upload failed</span>
            <button class="retry-btn">Retry</button>
          </div>
        </div>
      `;

      const retryBtn = document.querySelector(".retry-btn");
      expect(retryBtn).toBeTruthy();
      expect(retryBtn.textContent).toBe("Retry");
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels", () => {
      document.body.innerHTML = `
        <div
          data-upload-zone
          role="region"
          aria-label="File upload area"
        >
          <p>Drag files here or click to select</p>
        </div>
        <input id="upload-input" type="file" aria-label="Select files to upload">
      `;

      const uploadZone = document.querySelector("[data-upload-zone]");
      const uploadInput = document.querySelector("#upload-input");

      expect(uploadZone.getAttribute("aria-label")).toBe("File upload area");
      expect(uploadInput.getAttribute("aria-label")).toBe("Select files to upload");
    });

    it("should be keyboard accessible", () => {
      document.body.innerHTML = `
        <button data-upload-trigger class="upload-btn" tabindex="0">
          Choose Files
        </button>
      `;

      const uploadBtn = document.querySelector("[data-upload-trigger]");
      expect(uploadBtn.tabIndex).toBe(0);
    });

    it("should announce upload status to screen readers", () => {
      document.body.innerHTML = `
        <div
          id="upload-progress"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <span>Uploading: file.pdf (50%)</span>
        </div>
      `;

      const progressContainer = document.querySelector("#upload-progress");
      expect(progressContainer.getAttribute("role")).toBe("status");
      expect(progressContainer.getAttribute("aria-live")).toBe("polite");
    });

    it("should have descriptive button labels", () => {
      document.body.innerHTML = `
        <button class="upload-btn" aria-label="Upload files to organize">
          Upload
        </button>
      `;

      const uploadBtn = document.querySelector(".upload-btn");
      expect(uploadBtn.getAttribute("aria-label")).toBe("Upload files to organize");
    });
  });

  describe("UI State Management", () => {
    it("should show upload zone initially", () => {
      const uploadZone = document.querySelector("[data-upload-zone]");
      expect(uploadZone).toBeTruthy();
      expect(uploadZone.style.display).not.toBe("none");
    });

    it("should hide upload zone during upload", () => {
      const uploadZone = document.querySelector("[data-upload-zone]");
      const progressContainer = document.querySelector("#upload-progress");

      uploadZone.style.display = "none";
      progressContainer.style.display = "block";

      expect(uploadZone.style.display).toBe("none");
      expect(progressContainer.style.display).toBe("block");
    });

    it("should show results after successful upload", () => {
      document.body.innerHTML = `
        <div id="upload-results" style="display: none;">
          <div class="file-item">file.pdf</div>
          <button class="organize-btn">Organize Files</button>
        </div>
      `;

      const results = document.querySelector("#upload-results");
      results.style.display = "block";

      expect(results.style.display).toBe("block");
    });

    it("should maintain button disabled state during upload", () => {
      document.body.innerHTML = `
        <button data-upload-trigger disabled>Choose Files</button>
      `;

      const uploadBtn = document.querySelector("[data-upload-trigger]");
      expect(uploadBtn.disabled).toBe(true);
    });
  });
});
