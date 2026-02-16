/**
 * File Organizer API client for TypeScript/JavaScript.
 *
 * A lightweight wrapper around the Fetch API that provides typed
 * request/response handling for every endpoint.
 *
 * @example
 * ```ts
 * const client = new FileOrganizerClient({ baseUrl: "http://localhost:8000" });
 * const health = await client.health();
 * console.log(health.status);
 * ```
 */

import type {
  ClientOptions,
  ConfigUpdateRequest,
  ConfigResponse,
  DedupeScanResponse,
  DedupeExecuteResponse,
  DedupePreviewResponse,
  DeleteFileResponse,
  FileContentResponse,
  FileInfo,
  FileListParams,
  FileListResponse,
  HealthResponse,
  JobStatusResponse,
  MoveFileResponse,
  OrganizationResultResponse,
  OrganizeExecuteResponse,
  ScanResponse,
  StorageStatsResponse,
  SystemStatusResponse,
  TokenResponse,
  UserCreateRequest,
  UserResponse,
} from "./types";

const API_PREFIX = "/api/v1";

/** Error thrown for non-2xx HTTP responses. */
export class ClientError extends Error {
  public readonly statusCode: number;
  public readonly detail: string;

  constructor(message: string, statusCode: number, detail: string = "") {
    super(message);
    this.name = "ClientError";
    this.statusCode = statusCode;
    this.detail = detail;
  }
}

export class AuthenticationError extends ClientError {
  constructor(message: string, statusCode: number, detail: string = "") {
    super(message, statusCode, detail);
    this.name = "AuthenticationError";
  }
}

export class NotFoundError extends ClientError {
  constructor(message: string, statusCode: number, detail: string = "") {
    super(message, statusCode, detail);
    this.name = "NotFoundError";
  }
}

export class ServerError extends ClientError {
  constructor(message: string, statusCode: number, detail: string = "") {
    super(message, statusCode, detail);
    this.name = "ServerError";
  }
}

export class FileOrganizerClient {
  private readonly baseUrl: string;
  private readonly timeout: number;
  private headers: Record<string, string>;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "http://localhost:8000").replace(
      /\/$/,
      ""
    );
    this.timeout = options.timeout ?? 30000;
    this.headers = { "Content-Type": "application/json" };
    if (options.token) {
      this.headers["Authorization"] = `Bearer ${options.token}`;
    }
    if (options.apiKey) {
      this.headers["X-API-Key"] = options.apiKey;
    }
  }

  /** Update the Bearer token for subsequent requests. */
  setToken(token: string): void {
    this.headers["Authorization"] = `Bearer ${token}`;
  }

  // -- internal helpers -----------------------------------------------------

  private url(path: string): string {
    return `${this.baseUrl}${API_PREFIX}${path}`;
  }

  private async request<T>(
    method: string,
    url: string,
    options: {
      body?: unknown;
      params?: Record<string, string | number | boolean | undefined>;
      formData?: URLSearchParams;
    } = {}
  ): Promise<T> {
    const targetUrl = new URL(url);
    if (options.params) {
      for (const [key, value] of Object.entries(options.params)) {
        if (value !== undefined) {
          targetUrl.searchParams.set(key, String(value));
        }
      }
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    const headers = { ...this.headers };
    let body: string | URLSearchParams | undefined;
    if (options.formData) {
      body = options.formData;
      delete headers["Content-Type"];
    } else if (options.body !== undefined) {
      body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(targetUrl.toString(), {
        method,
        headers,
        body,
        signal: controller.signal,
      });

      if (!response.ok) {
        let detail = "";
        try {
          const errorBody = await response.json();
          detail = errorBody.detail ?? errorBody.message ?? "";
        } catch {
          try {
            detail = await response.text();
          } catch (error: unknown) {
            detail =
              error instanceof Error
                ? error.message
                : "Failed to parse error response body.";
          }
        }
        const message = `HTTP ${response.status}: ${detail}`;

        if (response.status === 401 || response.status === 403) {
          throw new AuthenticationError(message, response.status, detail);
        }
        if (response.status === 404) {
          throw new NotFoundError(message, response.status, detail);
        }
        if (response.status >= 500) {
          throw new ServerError(message, response.status, detail);
        }
        throw new ClientError(message, response.status, detail);
      }

      if (response.status === 204) {
        return undefined as unknown as T;
      }
      return (await response.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  // -- auth -----------------------------------------------------------------

  async login(username: string, password: string): Promise<TokenResponse> {
    const formData = new URLSearchParams();
    formData.set("username", username);
    formData.set("password", password);
    const tokens = await this.request<TokenResponse>(
      "POST",
      this.url("/auth/login"),
      { formData }
    );
    this.setToken(tokens.access_token);
    return tokens;
  }

  async register(data: UserCreateRequest): Promise<UserResponse> {
    return this.request<UserResponse>("POST", this.url("/auth/register"), {
      body: data,
    });
  }

  async refreshToken(refreshToken: string): Promise<TokenResponse> {
    const tokens = await this.request<TokenResponse>(
      "POST",
      this.url("/auth/refresh"),
      { body: { refresh_token: refreshToken } }
    );
    this.setToken(tokens.access_token);
    return tokens;
  }

  async me(): Promise<UserResponse> {
    return this.request<UserResponse>("GET", this.url("/auth/me"));
  }

  async logout(refreshToken: string): Promise<void> {
    await this.request<void>("POST", this.url("/auth/logout"), {
      body: { refresh_token: refreshToken },
    });
  }

  // -- health ---------------------------------------------------------------

  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("GET", this.url("/health"));
  }

  // -- files ----------------------------------------------------------------

  async listFiles(params: FileListParams): Promise<FileListResponse> {
    return this.request<FileListResponse>("GET", this.url("/files"), {
      params: {
        path: params.path,
        recursive: params.recursive,
        include_hidden: params.include_hidden,
        file_type: params.file_type,
        sort_by: params.sort_by,
        sort_order: params.sort_order,
        skip: params.skip,
        limit: params.limit,
      },
    });
  }

  async getFileInfo(path: string): Promise<FileInfo> {
    return this.request<FileInfo>("GET", this.url("/files/info"), {
      params: { path },
    });
  }

  async readFileContent(
    path: string,
    maxBytes?: number,
    encoding?: string
  ): Promise<FileContentResponse> {
    return this.request<FileContentResponse>(
      "GET",
      this.url("/files/content"),
      {
        params: { path, max_bytes: maxBytes, encoding },
      }
    );
  }

  async moveFile(
    source: string,
    destination: string,
    options: { overwrite?: boolean; dryRun?: boolean } = {}
  ): Promise<MoveFileResponse> {
    return this.request<MoveFileResponse>("POST", this.url("/files/move"), {
      body: {
        source,
        destination,
        overwrite: options.overwrite ?? false,
        dry_run: options.dryRun ?? false,
      },
    });
  }

  async deleteFile(
    path: string,
    options: { permanent?: boolean; dryRun?: boolean } = {}
  ): Promise<DeleteFileResponse> {
    return this.request<DeleteFileResponse>("DELETE", this.url("/files"), {
      body: {
        path,
        permanent: options.permanent ?? false,
        dry_run: options.dryRun ?? false,
      },
    });
  }

  // -- organize -------------------------------------------------------------

  async scan(
    inputDir: string,
    options: { recursive?: boolean; includeHidden?: boolean } = {}
  ): Promise<ScanResponse> {
    return this.request<ScanResponse>("POST", this.url("/organize/scan"), {
      body: {
        input_dir: inputDir,
        recursive: options.recursive ?? true,
        include_hidden: options.includeHidden ?? false,
      },
    });
  }

  async previewOrganize(
    inputDir: string,
    outputDir: string,
    options: { skipExisting?: boolean; useHardlinks?: boolean } = {}
  ): Promise<OrganizationResultResponse> {
    return this.request<OrganizationResultResponse>(
      "POST",
      this.url("/organize/preview"),
      {
        body: {
          input_dir: inputDir,
          output_dir: outputDir,
          skip_existing: options.skipExisting ?? true,
          dry_run: true,
          use_hardlinks: options.useHardlinks ?? true,
          run_in_background: false,
        },
      }
    );
  }

  async organize(
    inputDir: string,
    outputDir: string,
    options: {
      dryRun?: boolean;
      skipExisting?: boolean;
      useHardlinks?: boolean;
      runInBackground?: boolean;
    } = {}
  ): Promise<OrganizeExecuteResponse> {
    return this.request<OrganizeExecuteResponse>(
      "POST",
      this.url("/organize/execute"),
      {
        body: {
          input_dir: inputDir,
          output_dir: outputDir,
          dry_run: options.dryRun ?? false,
          skip_existing: options.skipExisting ?? true,
          use_hardlinks: options.useHardlinks ?? true,
          run_in_background: options.runInBackground ?? true,
        },
      }
    );
  }

  async getJob(jobId: string): Promise<JobStatusResponse> {
    return this.request<JobStatusResponse>(
      "GET",
      this.url(`/organize/status/${jobId}`)
    );
  }

  // -- system ---------------------------------------------------------------

  async systemStatus(path: string = "."): Promise<SystemStatusResponse> {
    return this.request<SystemStatusResponse>(
      "GET",
      this.url("/system/status"),
      { params: { path } }
    );
  }

  async getConfig(profile: string = "default"): Promise<ConfigResponse> {
    return this.request<ConfigResponse>("GET", this.url("/system/config"), {
      params: { profile },
    });
  }

  async updateConfig(payload: ConfigUpdateRequest): Promise<ConfigResponse> {
    return this.request<ConfigResponse>("PATCH", this.url("/system/config"), {
      body: payload,
    });
  }

  async systemStats(options: {
    path?: string;
    maxDepth?: number;
    useCache?: boolean;
  } = {}): Promise<StorageStatsResponse> {
    return this.request<StorageStatsResponse>("GET", this.url("/system/stats"), {
      params: {
        path: options.path ?? ".",
        max_depth: options.maxDepth,
        use_cache: options.useCache ?? true,
      },
    });
  }

  // -- dedupe ---------------------------------------------------------------

  async dedupeScan(
    path: string,
    options: {
      recursive?: boolean;
      algorithm?: "md5" | "sha256";
      minFileSize?: number;
      maxFileSize?: number;
    } = {}
  ): Promise<DedupeScanResponse> {
    return this.request<DedupeScanResponse>("POST", this.url("/dedupe/scan"), {
      body: {
        path,
        recursive: options.recursive ?? true,
        algorithm: options.algorithm ?? "sha256",
        min_file_size: options.minFileSize ?? 0,
        ...(options.maxFileSize !== undefined && {
          max_file_size: options.maxFileSize,
        }),
      },
    });
  }

  async dedupePreview(
    path: string,
    options: { recursive?: boolean; algorithm?: "md5" | "sha256" } = {}
  ): Promise<DedupePreviewResponse> {
    return this.request<DedupePreviewResponse>(
      "POST",
      this.url("/dedupe/preview"),
      {
        body: {
          path,
          recursive: options.recursive ?? true,
          algorithm: options.algorithm ?? "sha256",
        },
      }
    );
  }

  async dedupeExecute(
    path: string,
    options: {
      recursive?: boolean;
      algorithm?: "md5" | "sha256";
      dryRun?: boolean;
      trash?: boolean;
    } = {}
  ): Promise<DedupeExecuteResponse> {
    return this.request<DedupeExecuteResponse>(
      "POST",
      this.url("/dedupe/execute"),
      {
        body: {
          path,
          recursive: options.recursive ?? true,
          algorithm: options.algorithm ?? "sha256",
          dry_run: options.dryRun ?? true,
          trash: options.trash ?? true,
        },
      }
    );
  }
}

export default FileOrganizerClient;
