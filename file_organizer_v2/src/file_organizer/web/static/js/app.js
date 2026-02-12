(() => {
  const storageKey = "fo-theme";
  const root = document.documentElement;
  const toggle = document.querySelector("[data-theme-toggle]");
  let lastFocusedElement = null;

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
      modal.setAttribute("aria-hidden", "true");
      modal.innerHTML = "";
    }
    if (lastFocusedElement) {
      lastFocusedElement.focus();
      lastFocusedElement = null;
    }
  };

  let organizeEventSource = null;
  let organizeJobId = null;

  const closeOrganizeStream = () => {
    if (organizeEventSource) {
      organizeEventSource.close();
      organizeEventSource = null;
    }
    organizeJobId = null;
  };

  const dispatchOrganizeRefresh = () => {
    document.body.dispatchEvent(new Event("refreshHistory"));
    document.body.dispatchEvent(new Event("refreshStats"));
  };

  const refreshOrganizeProgress = async (statusUrl) => {
    const target = document.querySelector("#organize-progress");
    if (!target || !statusUrl) return;
    try {
      const response = await fetch(statusUrl, {
        headers: {
          "HX-Request": "true",
        },
      });
      if (!response.ok) return;
      target.innerHTML = await response.text();
      bindOrganizeDashboard();
    } catch (error) {
      // Ignore transient polling/network failures.
    }
  };

  const bindOrganizeDashboard = () => {
    const node = document.querySelector("[data-organize-job]");
    if (!node) {
      closeOrganizeStream();
      return;
    }

    const jobId = node.getAttribute("data-job-id");
    const status = node.getAttribute("data-job-status");
    const streamUrl = node.getAttribute("data-stream-url");
    const statusUrl = node.getAttribute("data-status-url");
    const terminal = status === "completed" || status === "failed";

    if (!jobId || !streamUrl || !statusUrl || terminal) {
      closeOrganizeStream();
      if (terminal) {
        dispatchOrganizeRefresh();
      }
      return;
    }

    if (organizeEventSource && organizeJobId === jobId) {
      return;
    }

    closeOrganizeStream();
    organizeJobId = jobId;
    organizeEventSource = new EventSource(streamUrl);
    organizeEventSource.addEventListener("status", () => {
      void refreshOrganizeProgress(statusUrl);
    });
    organizeEventSource.addEventListener("complete", () => {
      void refreshOrganizeProgress(statusUrl);
      dispatchOrganizeRefresh();
      closeOrganizeStream();
    });
    organizeEventSource.onerror = () => {
      closeOrganizeStream();
    };
  };

  const openModal = () => {
    const modal = document.querySelector("#preview-modal");
    if (!modal) return;
    lastFocusedElement =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    const focusTarget =
      modal.querySelector("button[data-modal-close]") ||
      modal.querySelector(
        "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"
      ) ||
      modal.querySelector("[data-modal-close]");
    if (focusTarget && focusTarget instanceof HTMLElement) {
      focusTarget.focus();
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
      const isDisabled = selected === 0;
      button.disabled = isDisabled;
      button.setAttribute("aria-disabled", isDisabled ? "true" : "false");
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

    if (!browser.dataset.bound) {
      browser.dataset.bound = "true";
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
    }

    updateSelection(browser);
  };

  document.body.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.matches("[data-tree-toggle]")) {
      const controlsId = target.getAttribute("aria-controls");
      const container = controlsId ? document.getElementById(controlsId) : null;
      if (!container) return;
      const isLoaded = target.dataset.loaded === "true";
      const isExpanded = target.getAttribute("aria-expanded") === "true";
      if (isLoaded) {
        if (isExpanded) {
          target.setAttribute("aria-expanded", "false");
          container.classList.add("is-collapsed");
        } else {
          target.setAttribute("aria-expanded", "true");
          container.classList.remove("is-collapsed");
        }
        event.preventDefault();
        event.stopPropagation();
      } else {
        target.setAttribute("aria-expanded", "true");
        container.classList.remove("is-collapsed");
      }
      return;
    }

    if (target.matches("[data-tree-link]")) {
      const tree = document.querySelector("#directory-tree");
      const path = target.getAttribute("data-tree-path");
      if (tree && path) {
        tree.setAttribute("hx-get", `/ui/files/tree?active=${path}`);
        if (window.htmx) {
          window.htmx.trigger(tree, "refresh");
        }
      }
    }

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
      openModal();
    }
    if (target && target.classList && target.classList.contains("tree-children")) {
      const toggle = document.querySelector(`[aria-controls="${target.id}"]`);
      if (toggle) {
        toggle.dataset.loaded = "true";
        toggle.setAttribute("aria-expanded", "true");
        target.classList.remove("is-collapsed");
      }
    }
    if (target && target.id === "file-results") {
      bindFileBrowser();
    }
    if (target && target.id === "organize-progress") {
      bindOrganizeDashboard();
    }
    if (target && target.id === "main") {
      bindFileBrowser();
      bindOrganizeDashboard();
    }
  });

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    const target = event.target;
    if (target && target.id === "preview-modal" && !event.detail.xhr.responseText) {
      closeModal();
    }
  });

  bindFileBrowser();
  bindOrganizeDashboard();
})();
