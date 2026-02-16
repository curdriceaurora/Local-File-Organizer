/**
 * Test utilities and helpers
 */

import { screen, waitFor } from "@testing-library/dom";
import userEvent from "@testing-library/user-event";

/**
 * Setup DOM for testing
 */
export function setupDOM() {
  document.body.innerHTML = "";
  localStorage.clear();
  sessionStorage.clear();
}

/**
 * Wait for element with timeout
 */
export async function waitForElement(selector, options = {}) {
  const { timeout = 3000 } = options;
  return waitFor(
    () => {
      const element = document.querySelector(selector);
      if (!element) {
        throw new Error(`Element not found: ${selector}`);
      }
      return element;
    },
    { timeout },
  );
}

/**
 * Simulate file upload
 */
export async function simulateFileUpload(inputSelector, files) {
  const input = document.querySelector(inputSelector);
  if (!input) {
    throw new Error(`Input not found: ${inputSelector}`);
  }

  const user = userEvent.setup();
  await user.upload(input, files);
  return input.files;
}

/**
 * Simulate drag and drop
 */
export async function simulateDragAndDrop(
  dropZoneSelector,
  files,
  options = {},
) {
  const dropZone = document.querySelector(dropZoneSelector);
  if (!dropZone) {
    throw new Error(`Drop zone not found: ${dropZoneSelector}`);
  }

  const dataTransfer = new DataTransfer();
  files.forEach((file) => dataTransfer.items.add(file));

  const dragOverEvent = new DragEvent("dragover", {
    bubbles: true,
    cancelable: true,
    dataTransfer,
  });
  const dropEvent = new DragEvent("drop", {
    bubbles: true,
    cancelable: true,
    dataTransfer,
  });

  dropZone.dispatchEvent(dragOverEvent);
  dropZone.dispatchEvent(dropEvent);

  return dataTransfer.files;
}

/**
 * Mock fetch response
 */
export function mockFetchResponse(data, options = {}) {
  const { status = 200, headers = {}, delay = 0 } = options;

  return new Promise((resolve) => {
    setTimeout(() => {
      resolve(
        new Response(JSON.stringify(data), {
          status,
          headers: {
            "Content-Type": "application/json",
            ...headers,
          },
        }),
      );
    }, delay);
  });
}

/**
 * Setup fetch mock with responses
 */
export function setupFetchMocks(responses = {}) {
  global.fetch = jest.fn(async (url, options) => {
    const urlStr = typeof url === "string" ? url : url.toString();
    const method = (options?.method || "GET").toUpperCase();
    const key = `${method} ${urlStr}`;

    if (responses[key]) {
      const response = responses[key];
      if (typeof response === "function") {
        return response();
      }
      return response;
    }

    return mockFetchResponse(
      { error: "Not mocked" },
      { status: 404 },
    );
  });

  return global.fetch;
}

/**
 * Setup EventSource mock
 */
export function mockEventSource(events = {}) {
  class MockEventSource {
    constructor(url) {
      this.url = url;
      this.listeners = {};
      this.readyState = 1;

      // Setup test events
      if (events[url]) {
        setTimeout(() => {
          events[url].forEach((event) => {
            this.dispatchEvent(event.type, event.data);
          });
        }, 0);
      }
    }

    addEventListener(type, callback) {
      if (!this.listeners[type]) {
        this.listeners[type] = [];
      }
      this.listeners[type].push(callback);
    }

    removeEventListener(type, callback) {
      if (this.listeners[type]) {
        this.listeners[type] = this.listeners[type].filter(
          (cb) => cb !== callback,
        );
      }
    }

    dispatchEvent(type, data) {
      if (this.listeners[type]) {
        this.listeners[type].forEach((callback) => {
          callback(new MessageEvent(type, { data }));
        });
      }
    }

    close() {
      this.readyState = 2;
    }
  }

  global.EventSource = MockEventSource;
  return MockEventSource;
}

/**
 * Trigger HTMX event
 */
export function triggerHTMXEvent(element, eventName, detail = {}) {
  const event = new CustomEvent(eventName, {
    detail,
    bubbles: true,
    cancelable: true,
  });
  element.dispatchEvent(event);
}

/**
 * Setup HTMX mock
 */
export function setupHTMXMock() {
  if (!window.htmx) {
    window.htmx = {
      trigger: jest.fn((target, event) => {
        triggerHTMXEvent(target, event);
      }),
      ajax: jest.fn(),
      config: {
        timeout: 0,
        defaultIndicatorStyle: "spinner",
      },
    };
  }
  return window.htmx;
}

/**
 * Wait for fetch to be called
 */
export async function waitForFetchCall(
  urlPattern,
  options = {},
) {
  const { timeout = 3000, count = 1 } = options;
  return waitFor(
    () => {
      const calls = global.fetch.mock.calls.filter((call) => {
        const url = typeof call[0] === "string" ? call[0] : call[0].toString();
        if (urlPattern instanceof RegExp) {
          return urlPattern.test(url);
        }
        return url.includes(urlPattern);
      });

      if (calls.length < count) {
        throw new Error(`Expected ${count} fetch calls to ${urlPattern}`);
      }
      return calls;
    },
    { timeout },
  );
}

/**
 * Check accessibility violations
 */
export async function checkAccessibility(container = document.body) {
  const { axe } = require("jest-axe");
  const results = await axe(container);
  return results;
}

/**
 * Take component snapshot
 */
export function takeSnapshot(container, name = "component") {
  expect(container.innerHTML).toMatchSnapshot(name);
}

export default {
  setupDOM,
  waitForElement,
  simulateFileUpload,
  simulateDragAndDrop,
  mockFetchResponse,
  setupFetchMocks,
  mockEventSource,
  triggerHTMXEvent,
  setupHTMXMock,
  waitForFetchCall,
  checkAccessibility,
  takeSnapshot,
};
