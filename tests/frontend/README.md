# Frontend Test Suite

Comprehensive testing infrastructure for the File Organizer v2.0 web interface.

## Overview

This test suite includes:
- **Component Tests**: Unit tests for UI components using Jest and Testing Library
- **E2E Tests**: End-to-end tests using Playwright
- **Responsive Tests**: Mobile and tablet viewport testing
- **Accessibility Tests**: A11y compliance checking with jest-axe
- **Mock Data**: Comprehensive fixtures for testing

## Setup

### Installation

```bash
npm install
```

### Playwright Browsers

Install browsers for E2E testing:

```bash
npx playwright install
```

## Running Tests

### Component Tests (Jest)

```bash
# Run all component tests
npm test

# Run in watch mode
npm test:watch

# Run with coverage report
npm test:coverage

# Run specific test file
npm test tests/frontend/component/test_file_upload.test.js
```

### E2E Tests (Playwright)

```bash
# Run all E2E tests
npm run test:e2e

# Run with UI (interactive mode)
npm run test:e2e:ui

# Run in debug mode
npm run test:e2e:debug

# Run specific test file
npm run test:e2e tests/frontend/e2e/test_organize_workflow.spec.js

# Run specific browser
npx playwright test --project=chromium
```

### Coverage Report

```bash
npm test:coverage
```

Coverage reports are generated in:
- Terminal output
- `coverage/` directory with HTML report

Open `coverage/index.html` in browser to view detailed coverage.

## Test Structure

```
tests/frontend/
├── component/              # Component unit tests
│   ├── test_file_upload.test.js
│   ├── test_progress_bar.test.js
│   ├── test_search_interface.test.js
│   └── test_settings_panel.test.js
├── e2e/                    # End-to-end tests
│   ├── test_organize_workflow.spec.js
│   ├── test_batch_operations.spec.js
│   ├── test_methodology_selection.spec.js
│   └── test_search_filtering.spec.js
├── responsive/             # Mobile & tablet tests
│   └── test_mobile_views.spec.js
├── fixtures/               # Test data & utilities
│   ├── mock-data.js        # Mock objects and data
│   └── test-utils.js       # Testing utilities
├── setup.js                # Jest setup file
└── README.md               # This file
```

## Writing Tests

### Component Test Template

```javascript
import { render, screen } from "@testing-library/dom";
import userEvent from "@testing-library/user-event";
import { setupDOM } from "../fixtures/test-utils.js";

describe("Component Name", () => {
  beforeEach(() => {
    setupDOM();
    // Setup component HTML or mount
  });

  it("should render correctly", () => {
    expect(screen.getByRole("button", { name: /submit/i })).toBeInTheDocument();
  });

  it("should handle user interaction", async () => {
    const user = userEvent.setup();
    const button = screen.getByRole("button");
    await user.click(button);
    // Assert expected behavior
  });
});
```

### E2E Test Template

```javascript
import { test, expect } from "@playwright/test";

test.describe("User Workflow", () => {
  test("should complete organize workflow", async ({ page }) => {
    await page.goto("/");
    await page.click("[data-upload-trigger]");
    // Perform user actions
    await expect(page.locator(".success-message")).toBeVisible();
  });
});
```

## Test Utilities

### Mock Data

```javascript
import { mockFiles, mockOrganizeJob, createMockFile } from "../fixtures/mock-data.js";
```

### Test Helpers

```javascript
import {
  setupDOM,
  waitForElement,
  simulateFileUpload,
  simulateDragAndDrop,
  setupFetchMocks,
  setupHTMXMock,
  checkAccessibility,
} from "../fixtures/test-utils.js";
```

## Testing HTMX Interactions

The test suite includes comprehensive HTMX testing support:

```javascript
import { setupHTMXMock, triggerHTMXEvent } from "../fixtures/test-utils.js";

test("HTMX interaction", () => {
  setupHTMXMock();
  // Test HTMX requests and responses
});
```

## Testing Accessibility

Use jest-axe for accessibility testing:

```javascript
import { checkAccessibility } from "../fixtures/test-utils.js";

test("should have no accessibility violations", async () => {
  const results = await checkAccessibility(document.body);
  expect(results).toHaveNoViolations();
});
```

## Mocking Fetch

```javascript
import { setupFetchMocks, mockFetchResponse } from "../fixtures/test-utils.js";

beforeEach(() => {
  setupFetchMocks({
    "GET /api/files": mockFetchResponse(mockFiles),
    "POST /api/organize": mockFetchResponse({ success: true }),
  });
});
```

## CI/CD Integration

Tests run automatically on:
- Pull requests
- Commits to main branch
- Scheduled nightly runs

### GitHub Actions

See `.github/workflows/` for CI configuration.

Run locally before pushing:

```bash
npm test
npm run test:e2e
```

## Debugging

### Jest Debugging

```bash
node --inspect-brk node_modules/.bin/jest tests/frontend/component/
# Then open chrome://inspect in Chrome
```

### Playwright Debugging

```bash
npm run test:e2e:debug
```

Opens Playwright Inspector for step-by-step debugging.

### Visual Debugging

E2E tests capture screenshots/videos on failure:
- Screenshots: `test-results/`
- Videos: `test-results/`

View HTML report:

```bash
npx playwright show-report
```

## Coverage Targets

- **Statements**: 70%
- **Branches**: 65%
- **Functions**: 70%
- **Lines**: 70%

## Browser Support

Tested on:
- Chrome/Chromium (latest)
- Firefox (latest)
- Safari/WebKit (latest)
- Edge (latest)
- Mobile Chrome (Pixel 5 emulation)
- Mobile Safari (iPhone 12 emulation)

## Known Issues & Gotchas

### Issue: Tests timeout on first run

**Solution**: Playwright needs to download browsers. Run `npx playwright install` first.

### Issue: localStorage/sessionStorage not available

**Solution**: Tests run in jsdom environment. Use global test utilities for storage.

### Issue: EventSource not working in tests

**Solution**: Use `setupHTMXMock()` and mock EventSource in setup.js.

### Issue: File upload tests fail

**Solution**: Use `simulateFileUpload()` or `simulateDragAndDrop()` test utilities.

### Issue: Fetch requests not mocked

**Solution**: Call `setupFetchMocks()` in test setup before making requests.

## Performance Tips

1. Run tests in parallel (default in Jest)
2. Use `test.only()` during development to run single test
3. Avoid `test.skip()` - delete or rewrite skipped tests
4. Mock external APIs - don't hit real servers
5. Use fixtures for heavy data

## Contributing

When adding new components/features:

1. Write component test first (TDD)
2. Write E2E test for user workflow
3. Add accessibility tests
4. Update mock data as needed
5. Ensure coverage >70%

## Resources

- [Jest Documentation](https://jestjs.io/)
- [Testing Library](https://testing-library.com/)
- [Playwright Documentation](https://playwright.dev/)
- [jest-axe](https://github.com/nickcolley/jest-axe)
- [Web Accessibility](https://www.w3.org/WAI/)

## Troubleshooting

### Tests fail locally but pass in CI

1. Check Node version: `node --version` (should be 18+)
2. Clear node_modules: `rm -rf node_modules && npm install`
3. Check for port conflicts: Ensure port 5000 is available
4. Kill old processes: `lsof -ti:5000 | xargs kill -9`

### Module not found errors

1. Check import paths use correct syntax
2. Verify files exist in expected location
3. Check moduleNameMapper in jest.config.js
4. Clear Jest cache: `jest --clearCache`

### HTMX tests failing

1. Verify window.htmx is mocked
2. Check htmx event names match implementation
3. Verify mock data matches expected structure

## Support

For issues or questions:
1. Check this README
2. Review test examples in the codebase
3. Check GitHub issues
4. Ask in project discussions
