/**
 * Desktop bridge utilities — wraps window.pywebview.api calls with safe
 * browser fallbacks so the same HTML works in both the native desktop app
 * (pywebview) and a regular browser session.
 *
 * All three entry-points check for window.pywebview before calling into the
 * native API, so they are silent no-ops in browser mode.
 *
 * Usage (available globally after this script loads):
 *
 *   window.desktopBrowseFile(inputId, fileTypes)
 *   window.desktopSaveFile(suggestedName, fileTypes)  → Promise<string>
 *   window.desktopOpenPath(path)
 */

(() => {
  "use strict";

  /**
   * Returns true when running inside the pywebview desktop app.
   * @returns {boolean}
   */
  const isDesktopApp = () =>
    typeof window.pywebview !== "undefined" &&
    window.pywebview !== null &&
    typeof window.pywebview.api !== "undefined";

  /**
   * Open a native file-picker dialog and populate a text input with the
   * selected absolute path.
   *
   * Tier 1 (desktop): window.pywebview.api.browse_file(fileTypes)
   * Tier 2 (browser): trigger a hidden <input type="file"> (returns only the
   *   filename, not the absolute path — caller should handle accordingly).
   *
   * @param {string} inputId  - id of the <input> element to populate.
   * @param {Array<Array<string>>} [fileTypes=[]] - Array of [description,
   *   glob_pattern] pairs.  Example: [['JSON files (*.json)', '*.json']].
   */
  window.desktopBrowseFile = function desktopBrowseFile(inputId, fileTypes) {
    fileTypes = fileTypes || [];

    if (isDesktopApp()) {
      window.pywebview.api
        .browse_file(fileTypes)
        .then(function (path) {
          if (path) {
            const el = document.getElementById(inputId);
            if (el) {
              el.value = path;
              el.dispatchEvent(new Event("change", { bubbles: true }));
            }
          }
        })
        .catch(function () {
          /* dialog cancelled or unavailable — no-op */
        });
      return;
    }

    // Browser fallback: trigger a hidden file input.
    const fallback = document.createElement("input");
    fallback.type = "file";
    if (fileTypes.length > 0) {
      // Build an accept attribute from the glob patterns (e.g. "*.json" → ".json").
      fallback.accept = fileTypes
        .map(function (pair) {
          return pair[1].replace(/^\*/, "");
        })
        .join(",");
    }
    fallback.style.display = "none";
    fallback.addEventListener("change", function () {
      if (fallback.files && fallback.files[0]) {
        const el = document.getElementById(inputId);
        if (el) {
          el.value = fallback.files[0].name;
          el.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }
      document.body.removeChild(fallback);
    });
    fallback.addEventListener("cancel", function () {
      document.body.removeChild(fallback);
    });
    document.body.appendChild(fallback);
    fallback.click();
  };

  /**
   * Open a native Save-As dialog and return the chosen destination path.
   *
   * Tier 1 (desktop): window.pywebview.api.save_file(suggestedName, fileTypes)
   * Tier 2 (browser): returns "" immediately (caller should fall back to a
   *   standard browser download link).
   *
   * @param {string} [suggestedName=""] - Pre-filled filename (no path separators).
   * @param {Array<Array<string>>} [fileTypes=[]] - Array of [description, glob] pairs.
   * @returns {Promise<string>} Resolved absolute destination path, or "" if
   *   the dialog was cancelled, unavailable, or we are in browser mode.
   */
  window.desktopSaveFile = function desktopSaveFile(suggestedName, fileTypes) {
    suggestedName = suggestedName || "";
    fileTypes = fileTypes || [];

    if (isDesktopApp()) {
      return window.pywebview.api
        .save_file(suggestedName, fileTypes)
        .catch(function () {
          return "";
        });
    }

    // No meaningful browser fallback for Save-As.
    return Promise.resolve("");
  };

  /**
   * Reveal *path* in the native file manager.
   *
   * Tier 1 (desktop): window.pywebview.api.open_path(path)
   * Tier 2 (browser): silent no-op (cannot open OS file manager from browser).
   *
   * @param {string} path - Absolute path to reveal.
   */
  window.desktopOpenPath = function desktopOpenPath(path) {
    if (!path) {
      return;
    }
    if (isDesktopApp()) {
      window.pywebview.api.open_path(path).catch(function () {
        /* open failed — no-op */
      });
    }
  };

  // Mark <body> so CSS can show/hide desktop-only elements.
  // Runs after DOMContentLoaded so the body element is guaranteed to exist.
  function applyDesktopMode() {
    if (isDesktopApp()) {
      document.body.dataset.desktopApp = "1";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyDesktopMode);
  } else {
    applyDesktopMode();
  }
})();
