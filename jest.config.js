export default {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/tests/frontend/setup.js"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/file_organizer_v2/src/file_organizer/web/static/$1",
  },
  transform: {
    "^.+\\.jsx?$": "babel-jest",
  },
  collectCoverageFrom: [
    "file_organizer_v2/src/file_organizer/web/static/**/*.js",
    "!**/*.min.js",
    "!**/node_modules/**",
    "!**/.git/**",
  ],
  coveragePathIgnorePatterns: [
    "/node_modules/",
    "/tests/",
  ],
  coverageThreshold: {
    global: {
      statements: 70,
      branches: 65,
      functions: 70,
      lines: 70,
    },
  },
  testMatch: [
    "tests/frontend/component/**/*.test.js",
    "tests/frontend/unit/**/*.test.js",
  ],
  testPathIgnorePatterns: [
    "/node_modules/",
    "/archive/",
  ],
  moduleFileExtensions: [
    "js",
    "jsx",
    "json",
  ],
  globals: {
    "ts-jest": {
      isolatedModules: true,
    },
  },
  verbose: true,
};
