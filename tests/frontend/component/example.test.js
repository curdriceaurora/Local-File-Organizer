/**
 * Example component test to verify Jest setup
 */

describe("Test Framework Setup", () => {
  it("should verify Jest is working", () => {
    expect(true).toBe(true);
  });

  it("should have DOM utilities available", () => {
    document.body.innerHTML = `<button id="test-button">Click me</button>`;
    const button = document.querySelector("#test-button");
    expect(button).toBeTruthy();
    expect(button.textContent).toBe("Click me");
  });

  it("should have localStorage available", () => {
    localStorage.setItem("test-key", "test-value");
    expect(localStorage.getItem("test-key")).toBe("test-value");
    localStorage.removeItem("test-key");
  });

  it("should have test utilities available", () => {
    expect(global.testUtils).toBeDefined();
    expect(global.testUtils.setLocalStorage).toBeDefined();
  });
});
