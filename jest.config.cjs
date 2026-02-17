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
    "<rootDir>/file_organizer_v2/src/file_organizer/web/static/**/*.{js,jsx}",
    "!<rootDir>/file_organizer_v2/src/file_organizer/web/static/**/app.js",
  ],
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
