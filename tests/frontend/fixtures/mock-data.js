/**
 * Mock data for testing
 */

export const mockFiles = [
  {
    id: "file-1",
    name: "document.pdf",
    size: 1024000,
    type: "application/pdf",
    modified: "2024-01-15",
    path: "/home/user/Documents/document.pdf",
  },
  {
    id: "file-2",
    name: "image.jpg",
    size: 2048000,
    type: "image/jpeg",
    modified: "2024-01-14",
    path: "/home/user/Pictures/image.jpg",
  },
  {
    id: "file-3",
    name: "spreadsheet.xlsx",
    size: 512000,
    type: "application/vnd.ms-excel",
    modified: "2024-01-13",
    path: "/home/user/Documents/spreadsheet.xlsx",
  },
];

export const mockOrganizeJob = {
  id: "job-123",
  status: "running",
  progress: 45,
  total: 100,
  processed: 45,
  errors: 0,
  startTime: "2024-01-15T10:00:00Z",
  estimatedTime: "2024-01-15T10:05:00Z",
};

export const mockOrganizeResult = {
  id: "job-123",
  status: "completed",
  summary: {
    total: 100,
    organized: 98,
    skipped: 1,
    errors: 1,
  },
  timeline: {
    start: "2024-01-15T10:00:00Z",
    end: "2024-01-15T10:05:00Z",
    duration: 300,
  },
};

export const mockMethodologies = [
  {
    id: "para",
    name: "PARA Method",
    description: "Projects, Areas, Resources, Archives",
    icon: "folder-open",
  },
  {
    id: "jd",
    name: "Johnny Decimal",
    description: "Decimal-based organizational system",
    icon: "list-ol",
  },
  {
    id: "gtd",
    name: "Getting Things Done",
    description: "Task management methodology",
    icon: "check-circle",
  },
];

export const mockSettings = {
  theme: "light",
  notifications: true,
  autoOrganize: false,
  defaultMethodology: "para",
  language: "en",
  timezone: "UTC",
};

export const mockOrganizationRules = [
  {
    id: "rule-1",
    name: "PDF Documents",
    pattern: "*.pdf",
    destination: "Documents/PDFs",
    enabled: true,
  },
  {
    id: "rule-2",
    name: "Images",
    pattern: "*.{jpg,png,gif}",
    destination: "Pictures/Imports",
    enabled: true,
  },
  {
    id: "rule-3",
    name: "Archives",
    pattern: "*.{zip,7z,rar}",
    destination: "Archives",
    enabled: false,
  },
];

export const mockSearchResults = [
  {
    id: "result-1",
    name: "annual_report_2023.pdf",
    path: "/Documents/2023/annual_report_2023.pdf",
    type: "document",
    size: 2048000,
    modified: "2023-12-31",
    score: 0.95,
  },
  {
    id: "result-2",
    name: "report_draft.pdf",
    path: "/Documents/Drafts/report_draft.pdf",
    type: "document",
    size: 1024000,
    modified: "2024-01-10",
    score: 0.87,
  },
];

export const mockApiError = {
  code: "ERR_INVALID_FILE",
  message: "Invalid file type",
  details: "File type .exe is not allowed",
};

/**
 * Create a mock file for upload testing
 */
export function createMockFile(
  name = "test.txt",
  size = 1024,
  type = "text/plain",
) {
  const blob = new Blob(["a".repeat(size)], { type });
  blob.name = name;
  blob.lastModified = Date.now();
  blob.lastModifiedDate = new Date();
  return blob;
}

/**
 * Create a mock FileList for input element
 */
export function createMockFileList(files = []) {
  const fileList = {
    length: files.length,
    item: (index) => files[index] || null,
  };
  return Object.assign(files, fileList);
}

/**
 * Create mock FormData
 */
export function createMockFormData(fields = {}) {
  const formData = new FormData();
  Object.entries(fields).forEach(([key, value]) => {
    formData.append(key, value);
  });
  return formData;
}
