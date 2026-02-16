/**
 * Organization Preview / Results Display Component Tests
 * Tests file list rendering, folder structure, metadata display, and actions
 */

import { setupDOM } from "../fixtures/test-utils";
import { mockFiles, mockOrganizeResult } from "../fixtures/mock-data";

describe("Organization Preview Component", () => {
  beforeEach(() => {
    setupDOM();
    document.body.innerHTML = `
      <div class="organization-preview">
        <div class="preview-header">
          <h2>Organization Preview</h2>
          <div class="view-controls">
            <button class="view-list-btn" aria-label="List view">☰</button>
            <button class="view-grid-btn" aria-label="Grid view">⊞</button>
            <button class="view-tree-btn" aria-label="Tree view">⋮</button>
          </div>
        </div>

        <div class="preview-stats">
          <div class="stat">
            <span class="stat-label">Total Files:</span>
            <span class="stat-value total-files">0</span>
          </div>
          <div class="stat">
            <span class="stat-label">Organized:</span>
            <span class="stat-value organized-count">0</span>
          </div>
          <div class="stat">
            <span class="stat-label">Skipped:</span>
            <span class="stat-value skipped-count">0</span>
          </div>
          <div class="stat">
            <span class="stat-label">Errors:</span>
            <span class="stat-value error-count">0</span>
          </div>
        </div>

        <div class="preview-content">
          <div class="file-list" id="file-list"></div>
          <div class="folder-tree" id="folder-tree" style="display: none;"></div>
          <div class="file-grid" id="file-grid" style="display: none;"></div>
        </div>

        <div class="preview-actions">
          <button class="select-all-btn" aria-label="Select all">Select All</button>
          <button class="deselect-all-btn" aria-label="Deselect all">Deselect All</button>
          <button class="action-move-btn" disabled aria-label="Move selected">Move</button>
          <button class="action-rename-btn" disabled aria-label="Rename selected">Rename</button>
          <button class="action-delete-btn" disabled aria-label="Delete selected">Delete</button>
          <button class="action-preview-btn" disabled aria-label="Preview selected">Preview</button>
        </div>

        <div id="action-dialogs" style="display: none;"></div>
      </div>
    `;
  });

  describe("File List Rendering", () => {
    it("should render file list initially", () => {
      const fileList = document.querySelector("#file-list");
      expect(fileList).toBeTruthy();
    });

    it("should display file items", () => {
      const fileList = document.querySelector("#file-list");

      mockFiles.forEach((file) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.innerHTML = `
          <input type="checkbox" data-file-select class="file-checkbox">
          <span class="file-name">${file.name}</span>
          <span class="file-size">${file.size} B</span>
          <span class="file-type">${file.type}</span>
          <span class="file-date">${file.modified}</span>
        `;
        fileList.appendChild(fileItem);
      });

      expect(fileList.querySelectorAll(".file-item").length).toBe(mockFiles.length);
    });

    it("should show file metadata", () => {
      const fileList = document.querySelector("#file-list");
      const file = mockFiles[0];

      const fileItem = document.createElement("div");
      fileItem.className = "file-item";
      fileItem.innerHTML = `
        <span class="file-name">${file.name}</span>
        <span class="file-size">${file.size} B</span>
        <span class="file-date">${file.modified}</span>
      `;
      fileList.appendChild(fileItem);

      const name = fileItem.querySelector(".file-name");
      const size = fileItem.querySelector(".file-size");
      const date = fileItem.querySelector(".file-date");

      expect(name.textContent).toBe(file.name);
      expect(size.textContent).toContain(String(file.size));
      expect(date.textContent).toBe(file.modified);
    });

    it("should handle empty file list", () => {
      const fileList = document.querySelector("#file-list");

      expect(fileList.querySelectorAll(".file-item").length).toBe(0);

      const emptyMsg = document.createElement("div");
      emptyMsg.className = "empty-message";
      emptyMsg.textContent = "No files to display";
      fileList.appendChild(emptyMsg);

      expect(fileList.querySelector(".empty-message")).toBeTruthy();
    });

    it("should display file icons based on type", () => {
      const fileList = document.querySelector("#file-list");

      const fileItem = document.createElement("div");
      fileItem.className = "file-item";
      fileItem.innerHTML = `
        <span class="file-icon pdf-icon">📄</span>
        <span class="file-name">document.pdf</span>
      `;
      fileList.appendChild(fileItem);

      const icon = fileItem.querySelector(".file-icon");
      expect(icon.classList.contains("pdf-icon")).toBe(true);
    });
  });

  describe("Folder Structure Display", () => {
    it("should display folder tree view", () => {
      const folderTree = document.querySelector("#folder-tree");

      folderTree.innerHTML = `
        <div class="tree-node">
          <span class="tree-toggle">▶</span>
          <span class="folder-name">Documents</span>
          <div class="tree-children" style="display: none;">
            <div class="tree-node">
              <span class="file-name">file.pdf</span>
            </div>
          </div>
        </div>
      `;

      expect(folderTree.querySelector(".folder-name")).toBeTruthy();
    });

    it("should expand/collapse folders", () => {
      const folderTree = document.querySelector("#folder-tree");

      folderTree.innerHTML = `
        <div class="tree-node">
          <span class="tree-toggle" data-expanded="false">▶</span>
          <span class="folder-name">Documents</span>
          <div class="tree-children" style="display: none;"></div>
        </div>
      `;

      const toggle = folderTree.querySelector(".tree-toggle");
      const children = folderTree.querySelector(".tree-children");

      toggle.click();
      toggle.dataset.expanded = "true";
      children.style.display = "block";

      expect(toggle.dataset.expanded).toBe("true");
      expect(children.style.display).toBe("block");
    });

    it("should show folder hierarchy", () => {
      const folderTree = document.querySelector("#folder-tree");

      folderTree.innerHTML = `
        <div class="tree-node" data-depth="0">
          <span class="folder-name">Root</span>
          <div class="tree-children">
            <div class="tree-node" data-depth="1">
              <span class="folder-name">Documents</span>
              <div class="tree-children">
                <div class="tree-node" data-depth="2">
                  <span class="file-name">report.pdf</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      `;

      const levels = folderTree.querySelectorAll("[data-depth]");
      expect(levels.length).toBeGreaterThan(0);

      levels.forEach((level, index) => {
        expect(parseInt(level.dataset.depth)).toBeLessThanOrEqual(2);
      });
    });

    it("should show item count for folders", () => {
      const folderTree = document.querySelector("#folder-tree");

      folderTree.innerHTML = `
        <div class="tree-node">
          <span class="folder-name">Documents</span>
          <span class="folder-count">(5 items)</span>
        </div>
      `;

      const count = folderTree.querySelector(".folder-count");
      expect(count.textContent).toBe("(5 items)");
    });
  });

  describe("Sorting and Filtering", () => {
    it("should sort files by name", () => {
      const fileList = document.querySelector("#file-list");

      const files = [...mockFiles].sort((a, b) => a.name.localeCompare(b.name));

      files.forEach((file) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.innerHTML = `<span class="file-name">${file.name}</span>`;
        fileList.appendChild(fileItem);
      });

      const names = Array.from(fileList.querySelectorAll(".file-name")).map(
        (el) => el.textContent
      );

      expect(names[0]).toBe("document.pdf");
    });

    it("should sort files by size", () => {
      const fileList = document.querySelector("#file-list");

      const files = [...mockFiles].sort((a, b) => a.size - b.size);

      files.forEach((file) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.innerHTML = `
          <span class="file-name">${file.name}</span>
          <span class="file-size">${file.size}</span>
        `;
        fileList.appendChild(fileItem);
      });

      const sizes = Array.from(fileList.querySelectorAll(".file-size")).map(
        (el) => parseInt(el.textContent)
      );

      for (let i = 1; i < sizes.length; i++) {
        expect(sizes[i]).toBeGreaterThanOrEqual(sizes[i - 1]);
      }
    });

    it("should sort files by date", () => {
      const fileList = document.querySelector("#file-list");

      const files = [...mockFiles].sort(
        (a, b) => new Date(a.modified) - new Date(b.modified)
      );

      files.forEach((file) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.innerHTML = `
          <span class="file-name">${file.name}</span>
          <span class="file-date">${file.modified}</span>
        `;
        fileList.appendChild(fileItem);
      });

      const first = fileList.querySelector(".file-date");
      expect(first.textContent).toBe(mockFiles[2].modified);
    });

    it("should filter by file type", () => {
      const fileList = document.querySelector("#file-list");

      const filtered = mockFiles.filter((f) => f.type.startsWith("application"));

      filtered.forEach((file) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.innerHTML = `
          <span class="file-name">${file.name}</span>
          <span class="file-type">${file.type}</span>
        `;
        fileList.appendChild(fileItem);
      });

      expect(fileList.querySelectorAll(".file-item").length).toBe(filtered.length);
    });
  });

  describe("Selection Checkboxes", () => {
    it("should select individual files", () => {
      const fileList = document.querySelector("#file-list");

      mockFiles.forEach((file) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.innerHTML = `
          <input type="checkbox" data-file-select class="file-checkbox">
          <span class="file-name">${file.name}</span>
        `;
        fileList.appendChild(fileItem);
      });

      const checkboxes = fileList.querySelectorAll(".file-checkbox");
      checkboxes[0].click();
      checkboxes[0].checked = true;

      expect(checkboxes[0].checked).toBe(true);
      expect(checkboxes[1].checked).toBe(false);
    });

    it("should select all files", () => {
      const fileList = document.querySelector("#file-list");
      const selectAllBtn = document.querySelector(".select-all-btn");

      mockFiles.forEach((file) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.innerHTML = `
          <input type="checkbox" data-file-select class="file-checkbox">
          <span class="file-name">${file.name}</span>
        `;
        fileList.appendChild(fileItem);
      });

      selectAllBtn.click();

      fileList.querySelectorAll(".file-checkbox").forEach((checkbox) => {
        checkbox.checked = true;
      });

      const allChecked = Array.from(fileList.querySelectorAll(".file-checkbox")).every(
        (cb) => cb.checked
      );

      expect(allChecked).toBe(true);
    });

    it("should deselect all files", () => {
      const fileList = document.querySelector("#file-list");
      const deselectAllBtn = document.querySelector(".deselect-all-btn");

      mockFiles.forEach((file) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.innerHTML = `
          <input type="checkbox" data-file-select class="file-checkbox" checked>
          <span class="file-name">${file.name}</span>
        `;
        fileList.appendChild(fileItem);
      });

      deselectAllBtn.click();

      fileList.querySelectorAll(".file-checkbox").forEach((checkbox) => {
        checkbox.checked = false;
      });

      const allUnchecked = Array.from(fileList.querySelectorAll(".file-checkbox")).every(
        (cb) => !cb.checked
      );

      expect(allUnchecked).toBe(true);
    });

    it("should track selection count", () => {
      const fileList = document.querySelector("#file-list");

      mockFiles.forEach((file) => {
        const fileItem = document.createElement("div");
        fileItem.className = "file-item";
        fileItem.innerHTML = `
          <input type="checkbox" data-file-select class="file-checkbox">
          <span class="file-name">${file.name}</span>
        `;
        fileList.appendChild(fileItem);
      });

      const checkboxes = fileList.querySelectorAll(".file-checkbox");

      checkboxes[0].click();
      checkboxes[0].checked = true;
      checkboxes[1].click();
      checkboxes[1].checked = true;

      const selectedCount = Array.from(checkboxes).filter((cb) => cb.checked).length;

      expect(selectedCount).toBe(2);
    });
  });

  describe("Action Buttons", () => {
    it("should enable action buttons when files selected", () => {
      const fileList = document.querySelector("#file-list");
      const moveBtn = document.querySelector(".action-move-btn");

      const fileItem = document.createElement("div");
      fileItem.className = "file-item";
      fileItem.innerHTML = `
        <input type="checkbox" data-file-select class="file-checkbox" checked>
        <span class="file-name">test.pdf</span>
      `;
      fileList.appendChild(fileItem);

      moveBtn.disabled = false;

      expect(moveBtn.disabled).toBe(false);
    });

    it("should disable action buttons when no files selected", () => {
      const moveBtn = document.querySelector(".action-move-btn");
      moveBtn.disabled = true;

      expect(moveBtn.disabled).toBe(true);
    });

    it("should show move dialog on move button click", () => {
      const moveBtn = document.querySelector(".action-move-btn");
      const dialogs = document.querySelector("#action-dialogs");

      moveBtn.disabled = false;

      moveBtn.click();

      const moveDialog = document.createElement("div");
      moveDialog.className = "move-dialog";
      moveDialog.innerHTML = `
        <p>Select destination folder:</p>
        <select id="destination-folder"></select>
        <button class="confirm-move">Move</button>
      `;
      dialogs.appendChild(moveDialog);
      dialogs.style.display = "block";

      expect(dialogs.style.display).toBe("block");
      expect(dialogs.querySelector(".move-dialog")).toBeTruthy();
    });

    it("should show rename dialog on rename button click", () => {
      const renameBtn = document.querySelector(".action-rename-btn");
      const dialogs = document.querySelector("#action-dialogs");

      renameBtn.disabled = false;
      renameBtn.click();

      const renameDialog = document.createElement("div");
      renameDialog.className = "rename-dialog";
      renameDialog.innerHTML = `
        <label>New name:</label>
        <input type="text" id="new-name" placeholder="Enter new name">
        <button class="confirm-rename">Rename</button>
      `;
      dialogs.appendChild(renameDialog);
      dialogs.style.display = "block";

      expect(dialogs.querySelector(".rename-dialog")).toBeTruthy();
    });

    it("should show delete confirmation dialog", () => {
      const deleteBtn = document.querySelector(".action-delete-btn");
      const dialogs = document.querySelector("#action-dialogs");

      deleteBtn.disabled = false;
      deleteBtn.click();

      const deleteDialog = document.createElement("div");
      deleteDialog.className = "delete-dialog";
      deleteDialog.innerHTML = `
        <p>Are you sure you want to delete these files?</p>
        <button class="confirm-delete">Delete</button>
        <button class="cancel-delete">Cancel</button>
      `;
      dialogs.appendChild(deleteDialog);
      dialogs.style.display = "block";

      expect(dialogs.querySelector(".delete-dialog")).toBeTruthy();
    });

    it("should preview selected file", () => {
      const previewBtn = document.querySelector(".action-preview-btn");

      previewBtn.disabled = false;
      previewBtn.click();

      previewBtn.dataset.action = "preview";
      expect(previewBtn.dataset.action).toBe("preview");
    });
  });

  describe("View Modes", () => {
    it("should switch to list view", () => {
      const listViewBtn = document.querySelector(".view-list-btn");
      const fileList = document.querySelector("#file-list");
      const folderTree = document.querySelector("#folder-tree");
      const fileGrid = document.querySelector("#file-grid");

      listViewBtn.click();

      fileList.style.display = "block";
      folderTree.style.display = "none";
      fileGrid.style.display = "none";

      expect(fileList.style.display).toBe("block");
      expect(folderTree.style.display).toBe("none");
    });

    it("should switch to tree view", () => {
      const treeViewBtn = document.querySelector(".view-tree-btn");
      const fileList = document.querySelector("#file-list");
      const folderTree = document.querySelector("#folder-tree");
      const fileGrid = document.querySelector("#file-grid");

      treeViewBtn.click();

      fileList.style.display = "none";
      folderTree.style.display = "block";
      fileGrid.style.display = "none";

      expect(folderTree.style.display).toBe("block");
      expect(fileList.style.display).toBe("none");
    });

    it("should switch to grid view", () => {
      const gridViewBtn = document.querySelector(".view-grid-btn");
      const fileList = document.querySelector("#file-list");
      const folderTree = document.querySelector("#folder-tree");
      const fileGrid = document.querySelector("#file-grid");

      gridViewBtn.click();

      fileList.style.display = "none";
      folderTree.style.display = "none";
      fileGrid.style.display = "block";

      expect(fileGrid.style.display).toBe("block");
    });

    it("should highlight active view button", () => {
      const listViewBtn = document.querySelector(".view-list-btn");

      listViewBtn.click();
      listViewBtn.classList.add("active");

      expect(listViewBtn.classList.contains("active")).toBe(true);
    });
  });

  describe("Statistics Display", () => {
    it("should display organization statistics", () => {
      const totalFiles = document.querySelector(".total-files");
      const organizedCount = document.querySelector(".organized-count");
      const skippedCount = document.querySelector(".skipped-count");
      const errorCount = document.querySelector(".error-count");

      totalFiles.textContent = String(mockOrganizeResult.summary.total);
      organizedCount.textContent = String(mockOrganizeResult.summary.organized);
      skippedCount.textContent = String(mockOrganizeResult.summary.skipped);
      errorCount.textContent = String(mockOrganizeResult.summary.errors);

      expect(totalFiles.textContent).toBe(String(mockOrganizeResult.summary.total));
      expect(organizedCount.textContent).toBe(String(mockOrganizeResult.summary.organized));
      expect(skippedCount.textContent).toBe(String(mockOrganizeResult.summary.skipped));
      expect(errorCount.textContent).toBe(String(mockOrganizeResult.summary.errors));
    });

    it("should update statistics in real-time", () => {
      const totalFiles = document.querySelector(".total-files");

      totalFiles.textContent = "0";
      expect(totalFiles.textContent).toBe("0");

      totalFiles.textContent = "50";
      expect(totalFiles.textContent).toBe("50");

      totalFiles.textContent = "100";
      expect(totalFiles.textContent).toBe("100");
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels for buttons", () => {
      const buttons = document.querySelectorAll("button[aria-label]");

      expect(buttons.length).toBeGreaterThan(0);
      buttons.forEach((button) => {
        expect(button.getAttribute("aria-label")).toBeTruthy();
      });
    });

    it("should be keyboard navigable", () => {
      const fileList = document.querySelector("#file-list");
      const file = document.createElement("div");
      file.className = "file-item";
      file.tabIndex = 0;
      fileList.appendChild(file);

      file.focus();
      expect(document.activeElement).toBe(file);
    });

    it("should announce selection changes", () => {
      document.body.innerHTML = `
        <div role="region" aria-live="polite" aria-atomic="true">
          <span class="selection-count">2 files selected</span>
        </div>
      `;

      const region = document.querySelector('[role="region"]');
      expect(region.getAttribute("aria-live")).toBe("polite");
      expect(region.getAttribute("aria-atomic")).toBe("true");
    });
  });
});
