/**
 * Jest setup file
 * Runs before all tests
 */

import "@testing-library/jest-dom";
import { toHaveNoViolations } from "jest-axe";

// Extend Jest matchers
expect.extend(toHaveNoViolations);

// Setup global test utilities
global.testUtils = {
  // Mock localStorage
  setLocalStorage: (key, value) => {
    localStorage.setItem(key, value);
  },
  getLocalStorage: (key) => localStorage.getItem(key),
  clearLocalStorage: () => localStorage.clear(),

  // Mock sessionStorage
  setSessionStorage: (key, value) => {
    sessionStorage.setItem(key, value);
  },
  getSessionStorage: (key) => sessionStorage.getItem(key),
  clearSessionStorage: () => sessionStorage.clear(),
};

// Mock EventSource for SSE tests
global.EventSource = jest.fn(() => ({
  addEventListener: jest.fn(),
  removeEventListener: jest.fn(),
  close: jest.fn(),
}));

// Mock fetch if not available
if (typeof global.fetch === "undefined") {
  global.fetch = jest.fn();
}

// Polyfill DataTransfer for drag-and-drop tests
if (typeof global.DataTransfer === "undefined") {
  class DataTransfer {
    constructor() {
      this._files = [];
      this._items = {
        add: (file) => {
          this._files.push(file);
        },
      };
    }

    get items() {
      return this._items;
    }

    get files() {
      return this._files;
    }
  }

  global.DataTransfer = DataTransfer;
}

// Polyfill DragEvent
if (typeof global.DragEvent === "undefined") {
  class DragEvent extends MouseEvent {
    constructor(type, eventInitDict = {}) {
      super(type, eventInitDict);
      this.dataTransfer = eventInitDict.dataTransfer || null;
    }
  }

  global.DragEvent = DragEvent;
}

// Suppress console errors during tests (optional)
const originalError = console.error;
beforeAll(() => {
  console.error = (...args) => {
    const msg = typeof args[0] === "string" ? args[0] : (args[0] instanceof Error ? args[0].message : "");
    if (
      msg.includes("Not implemented: HTMLFormElement.prototype.submit") ||
      msg.includes("Not implemented: HTMLFormElement.prototype.requestSubmit")
    ) {
      return;
    }
    originalError.call(console, ...args);
  };
});

afterAll(() => {
  console.error = originalError;
});

// Cleanup after each test
afterEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});
