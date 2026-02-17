module.exports = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/tests/frontend/setup.js"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/file_organizer_v2/src/file_organizer/web/static/$1",
  },
  transform: {
    "^.+\\.jsx?$": "babel-jest",
  },
  coveragePathIgnorePatterns: [
    "/node_modules/",
    "/tests/",
    ".*\\.min\\.js$",
  ],
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
