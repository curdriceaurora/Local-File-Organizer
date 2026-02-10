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
})();
