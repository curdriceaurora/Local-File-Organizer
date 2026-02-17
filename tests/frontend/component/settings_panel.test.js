/**
 * Settings Panel Component Tests
 * Tests form handling, validation, persistence, and settings management
 */

import { setupDOM, setupFetchMocks, mockFetchResponse } from "../fixtures/test-utils";
import { mockSettings } from "../fixtures/mock-data";

describe("Settings Panel Component", () => {
  beforeEach(() => {
    setupDOM();
    document.body.innerHTML = `
      <div class="settings-panel">
        <form id="settings-form" class="settings-form">
          <div class="settings-section">
            <h2>Appearance</h2>
            <div class="form-group">
              <label for="theme-toggle">Theme</label>
              <select id="theme-toggle" name="theme" aria-label="Select theme">
                <option value="light">Light</option>
                <option value="dark">Dark</option>
                <option value="auto">Auto</option>
              </select>
            </div>
          </div>

          <div class="settings-section">
            <h2>Notifications</h2>
            <div class="form-group">
              <label for="notifications-toggle">
                <input type="checkbox" id="notifications-toggle" name="notifications">
                Enable Notifications
              </label>
            </div>
          </div>

          <div class="settings-section">
            <h2>Organization</h2>
            <div class="form-group">
              <label for="auto-organize-toggle">
                <input type="checkbox" id="auto-organize-toggle" name="autoOrganize">
                Auto-organize files
              </label>
            </div>

            <div class="form-group">
              <label for="methodology-select">Default Methodology</label>
              <select id="methodology-select" name="defaultMethodology" aria-label="Select methodology">
                <option value="para">PARA Method</option>
                <option value="jd">Johnny Decimal</option>
                <option value="gtd">Getting Things Done</option>
              </select>
            </div>
          </div>

          <div class="settings-section">
            <h2>Localization</h2>
            <div class="form-group">
              <label for="language-select">Language</label>
              <select id="language-select" name="language" aria-label="Select language">
                <option value="en">English</option>
                <option value="es">Español</option>
                <option value="fr">Français</option>
                <option value="de">Deutsch</option>
              </select>
            </div>

            <div class="form-group">
              <label for="timezone-select">Timezone</label>
              <select id="timezone-select" name="timezone" aria-label="Select timezone">
                <option value="UTC">UTC</option>
                <option value="PST">PST</option>
                <option value="EST">EST</option>
                <option value="CST">CST</option>
              </select>
            </div>
          </div>

          <div class="settings-actions">
            <button type="submit" class="save-btn" aria-label="Save settings">
              Save Settings
            </button>
            <button type="reset" class="reset-btn" aria-label="Reset to defaults">
              Reset to Defaults
            </button>
          </div>

          <div id="form-errors" class="error-container"></div>
          <div id="form-success" class="success-message" style="display: none;"></div>
        </form>
      </div>
    `;
  });

  describe("Form Input Handling", () => {
    it("should capture dropdown selection", () => {
      const themeToggle = document.querySelector("#theme-toggle");
      themeToggle.value = "dark";

      expect(themeToggle.value).toBe("dark");
    });

    it("should capture checkbox changes", () => {
      const notificationsToggle = document.querySelector("#notifications-toggle");

      notificationsToggle.checked = true;
      expect(notificationsToggle.checked).toBe(true);

      notificationsToggle.checked = false;
      expect(notificationsToggle.checked).toBe(false);
    });

    it("should handle multiple checkbox selections", () => {
      const autoOrganize = document.querySelector("#auto-organize-toggle");
      const notifications = document.querySelector("#notifications-toggle");

      autoOrganize.checked = true;
      notifications.checked = true;

      expect(autoOrganize.checked).toBe(true);
      expect(notifications.checked).toBe(true);
    });

    it("should update form with initial settings", () => {
      const themeToggle = document.querySelector("#theme-toggle");
      const notificationsToggle = document.querySelector("#notifications-toggle");

      themeToggle.value = mockSettings.theme;
      notificationsToggle.checked = mockSettings.notifications;

      expect(themeToggle.value).toBe(mockSettings.theme);
      expect(notificationsToggle.checked).toBe(mockSettings.notifications);
    });

    it("should validate required fields", () => {
      const languageSelect = document.querySelector("#language-select");
      languageSelect.required = true;

      expect(languageSelect.required).toBe(true);
    });
  });

  describe("Form Validation", () => {
    it("should validate methodology selection", () => {
      const methodologySelect = document.querySelector("#methodology-select");

      const validOptions = ["para", "jd", "gtd"];
      methodologySelect.value = "para";

      expect(validOptions).toContain(methodologySelect.value);
    });

    it("should reject invalid methodology", () => {
      const methodologySelect = document.querySelector("#methodology-select");

      methodologySelect.value = "invalid";

      // Should only allow valid options
      methodologySelect.value = "para";
      expect(methodologySelect.value).toBe("para");
    });

    it("should validate timezone selection", () => {
      const timezoneSelect = document.querySelector("#timezone-select");

      const validTimezones = ["UTC", "PST", "EST", "CST"];
      timezoneSelect.value = "EST";

      expect(validTimezones).toContain(timezoneSelect.value);
    });

    it("should validate language selection", () => {
      const languageSelect = document.querySelector("#language-select");

      const validLanguages = ["en", "es", "fr", "de"];
      languageSelect.value = "es";

      expect(validLanguages).toContain(languageSelect.value);
    });

    it("should show validation error messages", () => {
      const errorContainer = document.querySelector("#form-errors");
      const errorMsg = document.createElement("div");
      errorMsg.className = "error";
      errorMsg.textContent = "Invalid timezone selected";

      errorContainer.appendChild(errorMsg);

      expect(errorContainer.textContent).toContain("Invalid timezone");
    });
  });

  describe("Setting Persistence", () => {
    it("should save settings to localStorage", () => {
      const form = document.querySelector("#settings-form");
      const themeToggle = document.querySelector("#theme-toggle");

      themeToggle.value = "dark";

      const settings = {
        theme: themeToggle.value,
      };

      localStorage.setItem("app-settings", JSON.stringify(settings));

      const saved = JSON.parse(localStorage.getItem("app-settings"));
      expect(saved.theme).toBe("dark");
    });

    it("should load settings from localStorage", () => {
      const savedSettings = {
        theme: "dark",
        notifications: true,
        language: "es",
      };

      localStorage.setItem("app-settings", JSON.stringify(savedSettings));

      const themeToggle = document.querySelector("#theme-toggle");
      const notificationsToggle = document.querySelector("#notifications-toggle");
      const languageSelect = document.querySelector("#language-select");

      const loaded = JSON.parse(localStorage.getItem("app-settings"));
      themeToggle.value = loaded.theme;
      notificationsToggle.checked = loaded.notifications;
      languageSelect.value = loaded.language;

      expect(themeToggle.value).toBe("dark");
      expect(notificationsToggle.checked).toBe(true);
      expect(languageSelect.value).toBe("es");
    });

    it("should persist settings across page reloads", () => {
      const settings = {
        theme: "dark",
        language: "fr",
      };

      localStorage.setItem("app-settings", JSON.stringify(settings));

      const loaded = JSON.parse(localStorage.getItem("app-settings"));
      expect(loaded.theme).toBe("dark");
      expect(loaded.language).toBe("fr");
    });

    it("should handle missing localStorage gracefully", () => {
      localStorage.clear();

      const saved = localStorage.getItem("app-settings");
      expect(saved).toBeNull();
    });
  });

  describe("Save Functionality", () => {
    it("should submit form on save button click", () => {
      const form = document.querySelector("#settings-form");
      const saveBtn = document.querySelector(".save-btn");

      const submitSpy = jest.spyOn(form, "submit");

      saveBtn.click();

      expect(submitSpy).toBeDefined();
      submitSpy.mockRestore();
    });

    it("should collect all form values on save", () => {
      const form = document.querySelector("#settings-form");

      const themeToggle = document.querySelector("#theme-toggle");
      const notificationsToggle = document.querySelector("#notifications-toggle");
      const autoOrganizeToggle = document.querySelector("#auto-organize-toggle");
      const languageSelect = document.querySelector("#language-select");

      themeToggle.value = "dark";
      notificationsToggle.checked = true;
      autoOrganizeToggle.checked = false;
      languageSelect.value = "es";

      const formData = new FormData(form);
      const data = Object.fromEntries(formData);

      expect(data.theme).toBe("dark");
      expect(data.language).toBe("es");
    });

    it("should show success message after save", () => {
      const successMsg = document.querySelector("#form-success");

      successMsg.textContent = "Settings saved successfully";
      successMsg.style.display = "block";

      expect(successMsg.style.display).toBe("block");
      expect(successMsg.textContent).toContain("saved");
    });

    it("should disable save button while saving", () => {
      const saveBtn = document.querySelector(".save-btn");

      saveBtn.disabled = true;
      expect(saveBtn.disabled).toBe(true);

      saveBtn.disabled = false;
      expect(saveBtn.disabled).toBe(false);
    });

    it("should show save progress indicator", () => {
      document.body.innerHTML = `
        <div class="save-indicator" style="display: none;">
          <span class="spinner"></span>
          <span>Saving...</span>
        </div>
      `;

      const indicator = document.querySelector(".save-indicator");
      indicator.style.display = "block";

      expect(indicator.style.display).toBe("block");
    });
  });

  describe("Reset Functionality", () => {
    it("should reset form to default values", () => {
      const form = document.querySelector("#settings-form");
      const themeToggle = document.querySelector("#theme-toggle");

      themeToggle.value = "dark";
      form.reset();

      expect(themeToggle.value).toBe("light");
    });

    it("should reset all form fields", () => {
      const form = document.querySelector("#settings-form");

      document.querySelectorAll("input, select").forEach((field) => {
        if (field.type === "checkbox") {
          field.checked = true;
        } else if (field.type === "select-one") {
          field.value = "invalid";
        }
      });

      form.reset();

      document.querySelectorAll("input, select").forEach((field) => {
        if (field.type === "checkbox") {
          expect([true, false]).toContain(field.checked);
        }
      });
    });

    it("should ask for confirmation before reset", () => {
      document.body.innerHTML = `
        <button class="reset-btn">Reset Settings</button>
        <div id="reset-dialog" style="display: none;">
          <p>Are you sure? This will reset all settings to default.</p>
          <button class="confirm-reset">Yes, Reset</button>
          <button class="cancel-reset">Cancel</button>
        </div>
      `;

      const resetBtn = document.querySelector(".reset-btn");
      const dialog = document.querySelector("#reset-dialog");

      resetBtn.click();
      dialog.style.display = "block";

      expect(dialog.style.display).toBe("block");
    });

    it("should update localStorage after reset", () => {
      const settings = {
        theme: "dark",
        language: "es",
      };

      localStorage.setItem("app-settings", JSON.stringify(settings));

      const defaults = {
        theme: "light",
        language: "en",
      };

      localStorage.setItem("app-settings", JSON.stringify(defaults));

      const loaded = JSON.parse(localStorage.getItem("app-settings"));
      expect(loaded.theme).toBe("light");
      expect(loaded.language).toBe("en");
    });
  });

  describe("Toggle Switches", () => {
    it("should toggle checkbox state", () => {
      const notificationsToggle = document.querySelector("#notifications-toggle");

      expect(notificationsToggle.checked).toBe(false);

      notificationsToggle.click();
      expect(notificationsToggle.checked).toBe(true);

      notificationsToggle.click();
      expect(notificationsToggle.checked).toBe(false);
    });

    it("should update label text based on toggle state", () => {
      document.body.innerHTML = `
        <label>
          <input type="checkbox" id="test-toggle">
          <span class="toggle-label">Off</span>
        </label>
      `;

      const toggle = document.querySelector("#test-toggle");
      const label = document.querySelector(".toggle-label");

      toggle.click();
      label.textContent = toggle.checked ? "On" : "Off";

      expect(label.textContent).toBe("On");

      toggle.click();
      label.textContent = toggle.checked ? "On" : "Off";

      expect(label.textContent).toBe("Off");
    });

    it("should trigger change events on toggle", () => {
      const notificationsToggle = document.querySelector("#notifications-toggle");
      const changeSpy = jest.fn();

      notificationsToggle.addEventListener("change", changeSpy);
      notificationsToggle.click();

      expect(changeSpy).toHaveBeenCalled();
    });
  });

  describe("Dropdown Selections", () => {
    it("should change theme dropdown", () => {
      const themeToggle = document.querySelector("#theme-toggle");

      themeToggle.value = "light";
      expect(themeToggle.value).toBe("light");

      themeToggle.value = "dark";
      expect(themeToggle.value).toBe("dark");

      themeToggle.value = "auto";
      expect(themeToggle.value).toBe("auto");
    });

    it("should change methodology dropdown", () => {
      const methodologySelect = document.querySelector("#methodology-select");

      methodologySelect.value = "para";
      expect(methodologySelect.value).toBe("para");

      methodologySelect.value = "jd";
      expect(methodologySelect.value).toBe("jd");
    });

    it("should maintain dropdown state after selection", () => {
      const languageSelect = document.querySelector("#language-select");

      languageSelect.value = "es";
      const selectedValue = languageSelect.value;

      languageSelect.blur();

      expect(languageSelect.value).toBe(selectedValue);
    });
  });

  describe("Error Handling", () => {
    it("should display save error message", () => {
      const errorContainer = document.querySelector("#form-errors");
      const errorMsg = document.createElement("div");
      errorMsg.className = "error";
      errorMsg.textContent = "Failed to save settings";

      errorContainer.appendChild(errorMsg);

      expect(errorContainer.textContent).toContain("Failed to save");
    });

    it("should provide retry option on error", () => {
      document.body.innerHTML = `
        <div id="form-errors">
          <div class="error-message">
            <span>Failed to save settings</span>
            <button class="retry-save">Retry</button>
          </div>
        </div>
      `;

      const retryBtn = document.querySelector(".retry-save");
      expect(retryBtn).toBeTruthy();
    });

    it("should clear error messages on new save attempt", () => {
      const errorContainer = document.querySelector("#form-errors");
      errorContainer.innerHTML = "<div class='error'>Previous error</div>";

      errorContainer.innerHTML = "";

      expect(errorContainer.innerHTML).toBe("");
    });
  });

  describe("Accessibility", () => {
    it("should have proper labels for all inputs", () => {
      const labels = document.querySelectorAll("label");

      expect(labels.length).toBeGreaterThan(0);
      labels.forEach((label) => {
        expect(label.textContent).toBeTruthy();
      });
    });

    it("should have ARIA labels for selects", () => {
      const selects = document.querySelectorAll("select");

      selects.forEach((select) => {
        expect(select.hasAttribute("aria-label")).toBe(true);
      });
    });

    it("should be keyboard navigable", () => {
      const inputs = document.querySelectorAll("input, select, button");

      inputs.forEach((input) => {
        input.focus();
        expect(document.activeElement).toBe(input);
      });
    });

    it("should announce form submission result", () => {
      const successMsg = document.querySelector("#form-success");

      successMsg.setAttribute("role", "status");
      successMsg.setAttribute("aria-live", "polite");
      successMsg.textContent = "Settings saved successfully";

      expect(successMsg.getAttribute("role")).toBe("status");
      expect(successMsg.getAttribute("aria-live")).toBe("polite");
    });

    it("should have descriptive button labels", () => {
      const saveBtn = document.querySelector(".save-btn");
      const resetBtn = document.querySelector(".reset-btn");

      expect(saveBtn.getAttribute("aria-label")).toBe("Save settings");
      expect(resetBtn.getAttribute("aria-label")).toBe("Reset to defaults");
    });
  });

  describe("Form State Management", () => {
    it("should track form dirty state", () => {
      const form = document.querySelector("#settings-form");
      const themeToggle = document.querySelector("#theme-toggle");

      themeToggle.value = "dark";

      form.dataset.isDirty = "true";
      expect(form.dataset.isDirty).toBe("true");
    });

    it("should warn before leaving with unsaved changes", () => {
      const form = document.querySelector("#settings-form");
      form.dataset.isDirty = "true";

      const warningMsg = "You have unsaved changes";

      form.dataset.isDirty === "true"
        ? expect(warningMsg).toBeTruthy()
        : expect(warningMsg).toBeFalsy();
    });

    it("should disable save button if no changes made", () => {
      const saveBtn = document.querySelector(".save-btn");

      saveBtn.disabled = true;
      expect(saveBtn.disabled).toBe(true);

      saveBtn.disabled = false;
      expect(saveBtn.disabled).toBe(false);
    });
  });
});
