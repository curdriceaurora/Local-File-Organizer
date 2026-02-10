(() => {
  const storageKey = "fo-theme";
  const root = document.documentElement;
  const toggle = document.querySelector("[data-theme-toggle]");

  const setTheme = (theme) => {
    root.dataset.theme = theme;
    if (toggle) {
      toggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      const chip = toggle.querySelector(".theme-toggle-chip");
      if (chip) {
        chip.textContent = theme === "dark" ? "Dark" : "Light";
      }
    }
    try {
      localStorage.setItem(storageKey, theme);
    } catch (error) {
      // Ignore storage failures (private mode, etc.)
    }
  };

  const stored = (() => {
    try {
      return localStorage.getItem(storageKey);
    } catch (error) {
      return null;
    }
  })();

  if (stored) {
    setTheme(stored);
  } else {
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    setTheme(prefersDark ? "dark" : "light");
  }

  if (toggle) {
    toggle.addEventListener("click", () => {
      const current = root.dataset.theme === "dark" ? "dark" : "light";
      setTheme(current === "dark" ? "light" : "dark");
    });
  }

  const closeModal = () => {
    document.body.classList.remove("modal-open");
    const modal = document.querySelector("#preview-modal");
    if (modal) {
      modal.innerHTML = "";
    }
  };

  const updateSelection = (browser) => {
    if (!browser) return;
    const selected = browser.querySelectorAll("[data-file-select]:checked").length;
    const count = browser.querySelector("[data-selection-count]");
    if (count) {
      count.textContent = `${selected} selected`;
    }
    browser.querySelectorAll("[data-bulk-action]").forEach((button) => {
      button.disabled = selected === 0;
    });
  };

  const bindFileBrowser = () => {
    const browser = document.querySelector("[data-file-browser]");
    if (!browser) return;

    const viewInput = browser.querySelector("#view-input");
    const limitInput = browser.querySelector("#limit-input");
    const form = browser.querySelector("#file-filters");

    browser.querySelectorAll("[data-view-toggle]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "true";
      button.addEventListener("click", () => {
        if (!viewInput || !form) return;
        viewInput.value = button.dataset.viewToggle;
        form.requestSubmit();
      });
    });

    if (form && limitInput && !form.dataset.bound) {
      form.dataset.bound = "true";
      form.addEventListener("change", (event) => {
        if (!limitInput.dataset.defaultLimit) return;
        if (event.target && event.target.matches("select, input")) {
          limitInput.value = limitInput.dataset.defaultLimit;
        }
      });
      form.addEventListener("input", (event) => {
        if (!limitInput.dataset.defaultLimit) return;
        if (event.target && event.target.matches("input[type='search']")) {
          limitInput.value = limitInput.dataset.defaultLimit;
        }
      });
    }

    const uploadForm = browser.querySelector("#upload-form");
    const uploadInput = browser.querySelector("#upload-input");
    const uploadZone = browser.querySelector("[data-upload-zone]");
    const uploadTrigger = browser.querySelector("[data-upload-trigger]");

    if (uploadZone && uploadInput && uploadForm && !uploadZone.dataset.bound) {
      uploadZone.dataset.bound = "true";
      const openPicker = () => uploadInput.click();

      uploadTrigger?.addEventListener("click", openPicker);
      uploadZone.addEventListener("click", (event) => {
        if (event.target === uploadZone) {
          openPicker();
        }
      });
      uploadZone.addEventListener("dragover", (event) => {
        event.preventDefault();
        uploadZone.classList.add("is-dragover");
      });
      uploadZone.addEventListener("dragleave", () => {
        uploadZone.classList.remove("is-dragover");
      });
      uploadZone.addEventListener("drop", (event) => {
        event.preventDefault();
        uploadZone.classList.remove("is-dragover");
        if (event.dataTransfer?.files?.length) {
          uploadInput.files = event.dataTransfer.files;
          uploadForm.requestSubmit();
        }
      });
      uploadInput.addEventListener("change", () => {
        if (uploadInput.files && uploadInput.files.length) {
          uploadForm.requestSubmit();
        }
      });
    }

    browser.addEventListener("change", (event) => {
      if (event.target && event.target.matches("[data-file-select]")) {
        updateSelection(browser);
      }
    });

    browser.addEventListener("keydown", (event) => {
      const activeCard = document.activeElement;
      if (!activeCard || !activeCard.matches("[data-file-card]")) return;

      const cards = Array.from(browser.querySelectorAll("[data-file-card]"));
      const index = cards.indexOf(activeCard);
      if (index === -1) return;

      let nextIndex = null;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") {
        nextIndex = Math.min(cards.length - 1, index + 1);
      } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        nextIndex = Math.max(0, index - 1);
      } else if (event.key === "Enter") {
        const previewButton = activeCard.querySelector("[data-preview-trigger]");
        const openButton = activeCard.querySelector("[data-open-trigger]");
        if (previewButton) previewButton.click();
        if (openButton) openButton.click();
      }

      if (nextIndex !== null && cards[nextIndex]) {
        cards[nextIndex].focus();
        event.preventDefault();
      }
    });

    updateSelection(browser);
  };

  document.body.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.matches("[data-modal-close]")) {
      closeModal();
      return;
    }

    if (target.matches("[data-context-action]")) {
      const menu = target.closest("[data-context-menu]");
      if (menu) {
        menu.classList.remove("is-open");
      }
      return;
    }

    if (target.matches("[data-context-trigger]")) {
      const menu = target.parentElement?.querySelector("[data-context-menu]");
      if (menu) {
        menu.classList.toggle("is-open");
      }
      return;
    }

    if (!target.closest("[data-context-menu]") && !target.matches("[data-context-trigger]")) {
      document.querySelectorAll("[data-context-menu].is-open").forEach((menu) => {
        menu.classList.remove("is-open");
      });
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.target;
    if (target && target.id === "preview-modal") {
      document.body.classList.add("modal-open");
    }
    if (target && target.id === "file-results") {
      bindFileBrowser();
    }
  });

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    const target = event.target;
    if (target && target.id === "preview-modal" && !event.detail.xhr.responseText) {
      closeModal();
    }
  });

  bindFileBrowser();
})();
