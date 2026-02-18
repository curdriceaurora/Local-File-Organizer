module.exports = {
  testEnvironment: "jsdom",
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/file_organizer/web/static/$1",
  },
  transform: {
    "^.+\\.jsx?$": "babel-jest",
  },
  collectCoverageFrom: [
    "<rootDir>/src/file_organizer/web/static/**/*.{js,jsx}",
    "!<rootDir>/src/file_organizer/web/static/**/app.js",
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
