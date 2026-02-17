module.exports = {
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
  coverageThreshold: {},
  testMatch: [
    "**/tests/frontend/**/*.test.js",
  ],
  moduleFileExtensions: [
    "js",
    "jsx",
    "json",
  ],
  verbose: true,
};
