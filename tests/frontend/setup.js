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

// Suppress console errors during tests (optional)
const originalError = console.error;
beforeAll(() => {
  console.error = (...args) => {
    if (
      typeof args[0] === "string" &&
      args[0].includes("Not implemented: HTMLFormElement.prototype.submit")
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
