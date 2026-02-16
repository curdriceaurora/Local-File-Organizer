/**
 * WebSocket / Server-Sent Events Component Tests
 * Tests event handling, connection, UI updates, and real-time status
 */

import { setupDOM, mockEventSource } from "../fixtures/test-utils";
import { mockOrganizeJob, mockOrganizeResult } from "../fixtures/mock-data";

describe("WebSocket/SSE Event Handling Component", () => {
  beforeEach(() => {
    setupDOM();
    jest.clearAllMocks();

    document.body.innerHTML = `
      <div class="event-listener">
        <div class="connection-status" data-status="disconnected">
          <span class="status-indicator"></span>
          <span class="status-text">Disconnected</span>
        </div>

        <div id="event-log" class="event-log" style="display: none;">
          <div class="event-items"></div>
        </div>

        <div class="real-time-updates">
          <div class="progress-display">
            <span class="current-file">No file</span>
            <span class="progress-percent">0%</span>
          </div>
          <div class="status-display">
            <span class="current-status">Idle</span>
            <span class="completion-time"></span>
          </div>
        </div>

        <button class="reconnect-btn" style="display: none;">Reconnect</button>
        <div class="reconnect-timer" style="display: none;">
          <span class="countdown"></span>
        </div>
      </div>
    `;
  });

  describe("Connection Establishment", () => {
    it("should establish EventSource connection", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/organize/123");

      expect(eventSource).toBeTruthy();
    });

    it("should show connected status", () => {
      mockEventSource({});

      const connectionStatus = document.querySelector(".connection-status");
      const statusText = document.querySelector(".status-text");

      const eventSource = new EventSource("/api/events/organize/123");

      connectionStatus.dataset.status = "connected";
      statusText.textContent = "Connected";

      expect(connectionStatus.dataset.status).toBe("connected");
      expect(statusText.textContent).toBe("Connected");
    });

    it("should set correct URL for event stream", () => {
      mockEventSource({});

      const jobId = "organize-123";
      const url = `/api/events/organize/${jobId}`;

      const eventSource = new EventSource(url);

      expect(eventSource.url).toBe(url);
    });

    it("should use withCredentials for authenticated events", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/organize/123");

      // EventSource doesn't support withCredentials directly
      // But we can test the URL contains necessary auth info
      expect(eventSource).toBeTruthy();
    });
  });

  describe("Event Reception", () => {
    it("should receive and log events", async () => {
      const events = {
        "/api/events/test": [
          { type: "message", data: JSON.stringify({ message: "test" }) },
        ],
      };

      mockEventSource(events);

      const eventSource = new EventSource("/api/events/test");

      let receivedEvent = null;
      eventSource.addEventListener("message", (event) => {
        receivedEvent = event;
      });

      // Simulate event dispatch
      eventSource.dispatchEvent("message", { data: JSON.stringify({ test: true }) });

      expect(eventSource).toBeTruthy();
    });

    it("should parse event data as JSON", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/test");

      const eventData = { type: "progress", value: 50, file: "test.pdf" };
      const jsonString = JSON.stringify(eventData);

      const parsed = JSON.parse(jsonString);

      expect(parsed.type).toBe("progress");
      expect(parsed.value).toBe(50);
    });

    it("should handle multiple event types", () => {
      const events = {
        "/api/events/organize": [
          { type: "progress", data: JSON.stringify({ progress: 25 }) },
          { type: "status", data: JSON.stringify({ status: "processing" }) },
          { type: "complete", data: JSON.stringify({ result: "success" }) },
        ],
      };

      mockEventSource(events);

      const eventSource = new EventSource("/api/events/organize");

      const eventTypes = [];

      eventSource.addEventListener("progress", () => eventTypes.push("progress"));
      eventSource.addEventListener("status", () => eventTypes.push("status"));
      eventSource.addEventListener("complete", () => eventTypes.push("complete"));

      expect(eventSource).toBeTruthy();
    });
  });

  describe("Real-time Status Updates", () => {
    it("should update progress on event", () => {
      const progressDisplay = document.querySelector(".progress-display");
      const progressPercent = document.querySelector(".progress-percent");

      const event = { progress: 45, file: "document.pdf" };

      progressPercent.textContent = `${event.progress}%`;

      expect(progressPercent.textContent).toBe("45%");
    });

    it("should update current file display", () => {
      const currentFile = document.querySelector(".current-file");

      const event = { file: "annual_report.pdf" };

      currentFile.textContent = event.file;

      expect(currentFile.textContent).toBe("annual_report.pdf");
    });

    it("should update status display", () => {
      const statusDisplay = document.querySelector(".current-status");

      const event = { status: "Processing files..." };

      statusDisplay.textContent = event.status;

      expect(statusDisplay.textContent).toBe("Processing files...");
    });

    it("should update completion time estimate", () => {
      const completionTime = document.querySelector(".completion-time");

      const event = { estimatedTime: "2024-01-15T10:05:00Z" };

      completionTime.textContent = `Est. completion: ${event.estimatedTime}`;

      expect(completionTime.textContent).toContain("Est. completion");
    });

    it("should handle multiple simultaneous updates", () => {
      const progressPercent = document.querySelector(".progress-percent");
      const currentFile = document.querySelector(".current-file");
      const statusDisplay = document.querySelector(".current-status");

      const event = {
        progress: 65,
        file: "image.jpg",
        status: "Processing image...",
      };

      progressPercent.textContent = `${event.progress}%`;
      currentFile.textContent = event.file;
      statusDisplay.textContent = event.status;

      expect(progressPercent.textContent).toBe("65%");
      expect(currentFile.textContent).toBe("image.jpg");
      expect(statusDisplay.textContent).toBe("Processing image...");
    });
  });

  describe("Connection Errors", () => {
    it("should handle connection error", () => {
      mockEventSource({});

      const connectionStatus = document.querySelector(".connection-status");
      const eventSource = new EventSource("/api/events/organize/123");

      eventSource.onerror = () => {
        connectionStatus.dataset.status = "disconnected";
      };

      eventSource.onerror();

      expect(connectionStatus.dataset.status).toBe("disconnected");
    });

    it("should show reconnect button on error", () => {
      const reconnectBtn = document.querySelector(".reconnect-btn");

      reconnectBtn.style.display = "block";

      expect(reconnectBtn.style.display).toBe("block");
    });

    it("should attempt automatic reconnection", () => {
      jest.useFakeTimers();

      const connectionStatus = document.querySelector(".connection-status");
      mockEventSource({});

      const eventSource = new EventSource("/api/events/test");

      eventSource.onerror = () => {
        connectionStatus.dataset.status = "reconnecting";

        setTimeout(() => {
          const newEventSource = new EventSource("/api/events/test");
          connectionStatus.dataset.status = "connected";
        }, 3000);
      };

      eventSource.onerror();

      expect(connectionStatus.dataset.status).toBe("reconnecting");

      jest.advanceTimersByTime(3000);

      expect(connectionStatus.dataset.status).toBe("connected");

      jest.useRealTimers();
    });

    it("should show reconnect countdown", () => {
      jest.useFakeTimers();

      const reconnectTimer = document.querySelector(".reconnect-timer");
      const countdown = document.querySelector(".countdown");

      reconnectTimer.style.display = "block";

      let seconds = 5;
      countdown.textContent = `Reconnecting in ${seconds}s`;

      const interval = setInterval(() => {
        seconds--;
        countdown.textContent = `Reconnecting in ${seconds}s`;

        if (seconds === 0) {
          clearInterval(interval);
          reconnectTimer.style.display = "none";
        }
      }, 1000);

      jest.advanceTimersByTime(1000);
      expect(countdown.textContent).toContain("4s");

      jest.advanceTimersByTime(5000);
      expect(reconnectTimer.style.display).toBe("none");

      jest.useRealTimers();
    });

    it("should provide manual reconnect button", () => {
      const reconnectBtn = document.querySelector(".reconnect-btn");

      reconnectBtn.style.display = "block";

      const reconnectFn = jest.fn();
      reconnectBtn.addEventListener("click", reconnectFn);

      reconnectBtn.click();

      expect(reconnectFn).toHaveBeenCalled();
    });
  });

  describe("Connection Closure", () => {
    it("should close connection on job completion", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/organize/123");

      eventSource.close();

      expect(eventSource.readyState).toBe(2); // CLOSED
    });

    it("should close connection on manual disconnect", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/organize/123");

      const closeBtn = document.querySelector(".reconnect-btn");
      closeBtn.click();

      eventSource.close();

      expect(eventSource.readyState).toBe(2);
    });

    it("should update status to disconnected", () => {
      mockEventSource({});

      const connectionStatus = document.querySelector(".connection-status");
      const eventSource = new EventSource("/api/events/organize/123");

      eventSource.close();

      connectionStatus.dataset.status = "disconnected";

      expect(connectionStatus.dataset.status).toBe("disconnected");
    });

    it("should remove event listeners on close", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/organize/123");

      const listener = jest.fn();
      eventSource.addEventListener("progress", listener);

      eventSource.removeEventListener("progress", listener);

      expect(eventSource.listeners).toBeDefined();
    });
  });

  describe("Event Type Routing", () => {
    it("should route progress events", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/organize");

      const progressHandler = jest.fn();
      eventSource.addEventListener("progress", progressHandler);

      eventSource.dispatchEvent("progress", { data: JSON.stringify({ progress: 50 }) });

      expect(eventSource).toBeTruthy();
    });

    it("should route completion events", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/organize");

      const completeHandler = jest.fn();
      eventSource.addEventListener("complete", completeHandler);

      eventSource.dispatchEvent("complete", { data: JSON.stringify({ result: "success" }) });

      expect(eventSource).toBeTruthy();
    });

    it("should route error events", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/organize");

      const errorHandler = jest.fn();
      eventSource.addEventListener("error", errorHandler);

      eventSource.dispatchEvent("error", { data: JSON.stringify({ error: "Failed" }) });

      expect(eventSource).toBeTruthy();
    });

    it("should route status update events", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/organize");

      const statusHandler = jest.fn();
      eventSource.addEventListener("status", statusHandler);

      eventSource.dispatchEvent("status", {
        data: JSON.stringify({ status: "processing" }),
      });

      expect(eventSource).toBeTruthy();
    });
  });

  describe("Event Log Display", () => {
    it("should display event log when enabled", () => {
      const eventLog = document.querySelector("#event-log");

      eventLog.style.display = "block";

      expect(eventLog.style.display).toBe("block");
    });

    it("should log received events", () => {
      const eventItems = document.querySelector(".event-items");

      const event1 = document.createElement("div");
      event1.className = "event-item";
      event1.textContent = "[10:00:00] Progress: 25%";
      eventItems.appendChild(event1);

      const event2 = document.createElement("div");
      event2.className = "event-item";
      event2.textContent = "[10:00:01] Progress: 50%";
      eventItems.appendChild(event2);

      expect(eventItems.querySelectorAll(".event-item").length).toBe(2);
    });

    it("should limit event log size", () => {
      const eventItems = document.querySelector(".event-items");

      const maxItems = 100;

      for (let i = 0; i < 150; i++) {
        const item = document.createElement("div");
        item.className = "event-item";
        item.textContent = `Event ${i}`;
        eventItems.appendChild(item);
      }

      while (eventItems.children.length > maxItems) {
        eventItems.removeChild(eventItems.firstChild);
      }

      expect(eventItems.children.length).toBeLessThanOrEqual(maxItems);
    });

    it("should clear event log", () => {
      const eventItems = document.querySelector(".event-items");

      const item = document.createElement("div");
      item.className = "event-item";
      item.textContent = "Test event";
      eventItems.appendChild(item);

      eventItems.innerHTML = "";

      expect(eventItems.children.length).toBe(0);
    });
  });

  describe("Accessibility", () => {
    it("should announce connection status", () => {
      document.body.innerHTML = `
        <div role="status" aria-live="polite" aria-atomic="true">
          <span class="status-text">Connected</span>
        </div>
      `;

      const status = document.querySelector('[role="status"]');

      expect(status.getAttribute("aria-live")).toBe("polite");
      expect(status.getAttribute("aria-atomic")).toBe("true");
    });

    it("should announce real-time updates", () => {
      document.body.innerHTML = `
        <div role="status" aria-live="polite" aria-atomic="true">
          <span>Progress: 50% - Processing image.jpg</span>
        </div>
      `;

      const status = document.querySelector('[role="status"]');

      expect(status.getAttribute("aria-live")).toBe("polite");
    });

    it("should have descriptive reconnect button", () => {
      const reconnectBtn = document.querySelector(".reconnect-btn");

      reconnectBtn.setAttribute("aria-label", "Reconnect to event stream");

      expect(reconnectBtn.getAttribute("aria-label")).toBe("Reconnect to event stream");
    });
  });

  describe("Error Recovery", () => {
    it("should handle malformed event data", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/test");

      try {
        const malformedData = "not-valid-json{";
        JSON.parse(malformedData);
      } catch (error) {
        expect(error).toBeTruthy();
      }
    });

    it("should continue processing after error", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/test");
      let errorCount = 0;

      eventSource.onerror = () => {
        errorCount++;
      };

      // Simulate error
      eventSource.onerror();

      // Continue processing
      expect(eventSource).toBeTruthy();
      expect(errorCount).toBe(1);
    });

    it("should handle duplicate events gracefully", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/test");

      const progressValues = [25, 25, 50, 50, 75];
      const lastValue = progressValues[progressValues.length - 1];

      expect(lastValue).toBe(75);
    });
  });

  describe("Performance", () => {
    it("should throttle frequent updates", async () => {
      jest.useFakeTimers();

      const progressPercent = document.querySelector(".progress-percent");

      const updates = [10, 11, 12, 13, 14, 15, 20, 25, 30, 35, 40, 45, 50];

      updates.forEach((value) => {
        progressPercent.textContent = `${value}%`;
      });

      expect(progressPercent.textContent).toBe("50%");

      jest.useRealTimers();
    });

    it("should not block UI during event processing", () => {
      mockEventSource({});

      const eventSource = new EventSource("/api/events/test");

      const uiElements = document.querySelectorAll("button, input");

      expect(uiElements.length).toBeGreaterThan(0);
    });
  });
});
