/**
 * TypeScript type definitions for the File Organizer API.
 *
 * These types mirror the server-side Pydantic models and provide
 * compile-time safety when consuming the API from TypeScript/JavaScript.
 */

// -- Health -----------------------------------------------------------------

export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
  timestamp: string;
}

// -- Auth -------------------------------------------------------------------

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  username: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
  last_login: string | null;
}

export interface UserCreateRequest {
  username: string;
  email: string;
  password: string;
  full_name?: string;
}

export interface TokenRefreshRequest {
  refresh_token: string;
}

// -- Files ------------------------------------------------------------------

export interface FileInfo {
  path: string;
  name: string;
  size: number;
  created: string;
  modified: string;
  file_type: string;
  mime_type: string | null;
}

export interface FileListResponse {
  items: FileInfo[];
  total: number;
  skip: number;
  limit: number;
}

export interface FileContentResponse {
  path: string;
  content: string;
  encoding: string;
  truncated: boolean;
  size: number;
  mime_type: string | null;
}

export interface MoveFileRequest {
  source: string;
  destination: string;
  overwrite?: boolean;
  allow_directory_overwrite?: boolean;
  dry_run?: boolean;
}

export interface MoveFileResponse {
  source: string;
  destination: string;
  moved: boolean;
  dry_run: boolean;
}

export interface DeleteFileRequest {
  path: string;
  permanent?: boolean;
  dry_run?: boolean;
}

export interface DeleteFileResponse {
  path: string;
  deleted: boolean;
  dry_run: boolean;
  trashed_path: string | null;
}

// -- Organize ---------------------------------------------------------------

export interface ScanRequest {
  input_dir: string;
  recursive?: boolean;
  include_hidden?: boolean;
}

export interface ScanResponse {
  input_dir: string;
  total_files: number;
  counts: Record<string, number>;
}

export interface OrganizationError {
  file: string;
  error: string;
}

export interface OrganizationResultResponse {
  total_files: number;
  processed_files: number;
  skipped_files: number;
  failed_files: number;
  processing_time: number;
  organized_structure: Record<string, string[]>;
  errors: OrganizationError[];
}

export interface OrganizeRequest {
  input_dir: string;
  output_dir: string;
  skip_existing?: boolean;
  dry_run?: boolean;
  use_hardlinks?: boolean;
  run_in_background?: boolean;
}

export interface OrganizeExecuteResponse {
  status: "queued" | "completed" | "failed";
  job_id: string | null;
  result: OrganizationResultResponse | null;
  error: string | null;
}

export interface JobStatusResponse {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  updated_at: string;
  result: OrganizationResultResponse | null;
  error: string | null;
}

// -- System -----------------------------------------------------------------

export interface SystemStatusResponse {
  app: string;
  version: string;
  environment: string;
  disk_total: number;
  disk_used: number;
  disk_free: number;
  active_jobs: number;
}

export interface ConfigResponse {
  profile: string;
  config: Record<string, unknown>;
  profiles: string[];
}

export interface ConfigUpdateRequest {
  profile?: string;
  default_methodology?: string;
  models?: Record<string, unknown>;
  updates?: Record<string, unknown>;
  watcher?: Record<string, unknown>;
  daemon?: Record<string, unknown>;
  parallel?: Record<string, unknown>;
  pipeline?: Record<string, unknown>;
  events?: Record<string, unknown>;
  deploy?: Record<string, unknown>;
  para?: Record<string, unknown>;
  johnny_decimal?: Record<string, unknown>;
}

export interface StorageStatsResponse {
  total_size: number;
  organized_size: number;
  saved_size: number;
  file_count: number;
  directory_count: number;
  size_by_type: Record<string, number>;
  largest_files: FileInfo[];
}

// -- Dedupe -----------------------------------------------------------------

export interface DedupeFileInfo {
  path: string;
  size: number;
  modified: string;
  accessed: string;
}

export interface DedupeGroup {
  hash_value: string;
  files: DedupeFileInfo[];
  total_size: number;
  wasted_space: number;
}

export interface DedupeScanRequest {
  path: string;
  recursive?: boolean;
  algorithm?: "md5" | "sha256";
  min_file_size?: number;
  max_file_size?: number;
  include_patterns?: string[];
  exclude_patterns?: string[];
}

export interface DedupeScanResponse {
  path: string;
  duplicates: DedupeGroup[];
  stats: Record<string, number>;
}

export interface DedupePreviewGroup {
  hash_value: string;
  keep: string;
  remove: string[];
}

export interface DedupePreviewResponse {
  path: string;
  preview: DedupePreviewGroup[];
  stats: Record<string, number>;
}

export interface DedupeExecuteResponse {
  path: string;
  removed: string[];
  dry_run: boolean;
  stats: Record<string, number>;
}

// -- Errors -----------------------------------------------------------------

export interface ApiErrorResponse {
  error: string;
  message: string;
  details?: unknown;
}

// -- Client options ---------------------------------------------------------

export interface ClientOptions {
  baseUrl?: string;
  apiKey?: string;
  token?: string;
  timeout?: number;
}

export interface FileListParams {
  path: string;
  recursive?: boolean;
  include_hidden?: boolean;
  file_type?: string;
  sort_by?: "name" | "size" | "created" | "modified";
  sort_order?: "asc" | "desc";
  skip?: number;
  limit?: number;
}
