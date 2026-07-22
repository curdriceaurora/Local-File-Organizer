"""Asynchronous API client for the File Organizer service.

Uses ``httpx.AsyncClient`` for HTTP transport and maps API responses to
typed Pydantic models.  This is the async counterpart of
:class:`~file_organizer.client.sync_client.FileOrganizerClient`.

Example::

    async with AsyncFileOrganizerClient(base_url="http://localhost:8000") as client:
        health = await client.health()
        print(health.status)
"""

from __future__ import annotations

from typing import Any, cast

import httpx

from file_organizer.client._organization import organization_request_payload
from file_organizer.client.exceptions import (
    AuthenticationError,
    ClientError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from file_organizer.client.models import (
    ConfigResponse,
    DedupeExecuteResponse,
    DedupePreviewResponse,
    DedupeScanResponse,
    DeleteFileResponse,
    FileContentResponse,
    FileInfo,
    FileListResponse,
    HealthResponse,
    JobStatusResponse,
    MoveFileResponse,
    OrganizationOptionsPayload,
    OrganizationPlanPayload,
    OrganizationResultResponse,
    OrganizeExecuteResponse,
    ScanResponse,
    StorageStatsResponse,
    SystemStatusResponse,
    TokenResponse,
    UserResponse,
)

_API_PREFIX = "/api/v1"


class AsyncFileOrganizerClient:
    """Asynchronous client for the File Organizer REST API.

    Args:
        base_url: Root URL of the API server (e.g. ``http://localhost:8000``).
        api_key: Optional pre-shared API key sent via ``X-API-Key`` header.
        token: Optional Bearer token for JWT authentication.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the async client with connection parameters."""
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if api_key:
            headers["X-API-Key"] = api_key
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
        )

    # -- helpers -------------------------------------------------------------

    def _url(self, path: str) -> str:
        """Build an API URL path."""
        return f"{_API_PREFIX}{path}"

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """Translate non-2xx responses into typed client exceptions."""
        if response.is_success:
            return

        status = response.status_code
        try:
            body = response.json()
        except Exception:
            body = {}
        detail = body.get("detail") or body.get("message") or response.text
        error_code = str(body.get("code") or body.get("error") or "")
        retryable = bool(body.get("retryable", False))
        details = body.get("details")
        message = f"HTTP {status}: {detail}"

        if status in (401, 403):
            raise AuthenticationError(
                message,
                status_code=status,
                detail=str(detail),
                error_code=error_code,
                retryable=retryable,
                details=details,
            )
        if status == 404:
            raise NotFoundError(
                message,
                status_code=status,
                detail=str(detail),
                error_code=error_code,
                retryable=retryable,
                details=details,
            )
        if status == 422:
            raise ValidationError(
                message,
                status_code=status,
                detail=str(detail),
                error_code=error_code,
                retryable=retryable,
                details=details,
            )
        if status >= 500:
            raise ServerError(
                message,
                status_code=status,
                detail=str(detail),
                error_code=error_code,
                retryable=retryable,
                details=details,
            )
        raise ClientError(
            message,
            status_code=status,
            detail=str(detail),
            error_code=error_code,
            retryable=retryable,
            details=details,
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        files: Any = None,
    ) -> dict[str, Any]:
        """Send a request for endpoints whose schema is intentionally open-ended."""
        response = await self._client.request(
            method,
            self._url(path),
            params=params,
            json=json,
            files=files,
        )
        self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return {}
        return cast(dict[str, Any], response.json())

    async def _request_list(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Send a request whose successful response is a JSON array."""
        response = await self._client.request(method, self._url(path), params=params)
        self._raise_for_status(response)
        return cast(list[Any], response.json())

    def set_token(self, token: str) -> None:
        """Update the Bearer token used for subsequent requests."""
        self._client.headers["Authorization"] = f"Bearer {token}"

    # -- auth ----------------------------------------------------------------

    async def login(self, username: str, password: str) -> TokenResponse:
        """Authenticate and obtain access and refresh tokens.

        Args:
            username: Account username.
            password: Account password.

        Returns:
            TokenResponse with access and refresh tokens.
        """
        response = await self._client.post(
            self._url("/auth/login"),
            data={"username": username, "password": password},
        )
        self._raise_for_status(response)
        tokens = TokenResponse.model_validate(response.json())
        self.set_token(tokens.access_token)
        return tokens

    async def register(
        self,
        username: str,
        email: str,
        password: str,
        full_name: str = "",
    ) -> UserResponse:
        """Register a new user account.

        Args:
            username: Desired username (3-32 characters).
            email: Valid email address.
            password: Account password.
            full_name: Optional full name.

        Returns:
            UserResponse for the newly created user.
        """
        payload: dict[str, str] = {
            "username": username,
            "email": email,
            "password": password,
        }
        if full_name:
            payload["full_name"] = full_name
        response = await self._client.post(self._url("/auth/register"), json=payload)
        self._raise_for_status(response)
        return UserResponse.model_validate(response.json())

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Refresh an expired access token.

        Args:
            refresh_token: The refresh token from a prior login.

        Returns:
            New TokenResponse with rotated tokens.
        """
        response = await self._client.post(
            self._url("/auth/refresh"),
            json={"refresh_token": refresh_token},
        )
        self._raise_for_status(response)
        tokens = TokenResponse.model_validate(response.json())
        self.set_token(tokens.access_token)
        return tokens

    async def me(self) -> UserResponse:
        """Get the current authenticated user profile.

        Returns:
            UserResponse for the authenticated user.
        """
        response = await self._client.get(self._url("/auth/me"))
        self._raise_for_status(response)
        return UserResponse.model_validate(response.json())

    async def logout(self, refresh_token: str) -> None:
        """Revoke the current access/refresh token pair.

        Args:
            refresh_token: Refresh token associated with the current login.
        """
        response = await self._client.post(
            self._url("/auth/logout"),
            json={"refresh_token": refresh_token},
        )
        self._raise_for_status(response)

    # -- health --------------------------------------------------------------

    async def health(self) -> HealthResponse:
        """Check API health.

        Returns:
            HealthResponse with status and version.
        """
        response = await self._client.get(self._url("/health"))
        self._raise_for_status(response)
        return HealthResponse.model_validate(response.json())

    # -- files ---------------------------------------------------------------

    async def list_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        include_hidden: bool = False,
        file_type: str | None = None,
        sort_by: str = "name",
        sort_order: str = "asc",
        skip: int = 0,
        limit: int = 100,
    ) -> FileListResponse:
        """List files in a directory.

        Args:
            path: Directory path to list.
            recursive: Whether to recurse into subdirectories.
            include_hidden: Whether to include hidden files.
            file_type: Comma-separated extensions or type groups to filter.
            sort_by: Sort field (name, size, created, modified).
            sort_order: Sort direction (asc, desc).
            skip: Number of items to skip (pagination).
            limit: Maximum items to return.

        Returns:
            FileListResponse with paginated file list.
        """
        params: dict[str, Any] = {
            "path": path,
            "recursive": recursive,
            "include_hidden": include_hidden,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "skip": skip,
            "limit": limit,
        }
        if file_type is not None:
            params["file_type"] = file_type
        response = await self._client.get(self._url("/files"), params=params)
        self._raise_for_status(response)
        return FileListResponse.model_validate(response.json())

    async def get_file_info(self, path: str) -> FileInfo:
        """Get metadata for a single file.

        Args:
            path: Absolute file path.

        Returns:
            FileInfo with file metadata.
        """
        response = await self._client.get(self._url("/files/info"), params={"path": path})
        self._raise_for_status(response)
        return FileInfo.model_validate(response.json())

    async def read_file_content(
        self,
        path: str,
        *,
        max_bytes: int = 200_000,
        encoding: str = "utf-8",
    ) -> FileContentResponse:
        """Read text content from a file.

        Args:
            path: Absolute file path.
            max_bytes: Maximum bytes to read.
            encoding: Text encoding to apply.

        Returns:
            FileContentResponse with the file content.
        """
        response = await self._client.get(
            self._url("/files/content"),
            params={"path": path, "max_bytes": max_bytes, "encoding": encoding},
        )
        self._raise_for_status(response)
        return FileContentResponse.model_validate(response.json())

    async def move_file(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> MoveFileResponse:
        """Move or rename a file.

        Args:
            source: Source file path.
            destination: Destination file path.
            overwrite: Allow overwriting existing files.
            dry_run: Preview only, do not perform the move.

        Returns:
            MoveFileResponse with the operation result.
        """
        response = await self._client.post(
            self._url("/files/move"),
            json={
                "source": source,
                "destination": destination,
                "overwrite": overwrite,
                "dry_run": dry_run,
            },
        )
        self._raise_for_status(response)
        return MoveFileResponse.model_validate(response.json())

    async def delete_file(
        self,
        path: str,
        *,
        permanent: bool = False,
        dry_run: bool = False,
    ) -> DeleteFileResponse:
        """Delete a file (trash or permanent).

        Args:
            path: File path to delete.
            permanent: If True, permanently delete instead of trashing.
            dry_run: Preview only, do not perform the delete.

        Returns:
            DeleteFileResponse with the operation result.
        """
        response = await self._client.request(
            "DELETE",
            self._url("/files"),
            json={"path": path, "permanent": permanent, "dry_run": dry_run},
        )
        self._raise_for_status(response)
        return DeleteFileResponse.model_validate(response.json())

    # -- organize ------------------------------------------------------------

    async def scan(
        self,
        input_dir: str,
        *,
        recursive: bool = True,
        include_hidden: bool = False,
    ) -> ScanResponse:
        """Scan a directory to count files by type.

        Args:
            input_dir: Directory path to scan.
            recursive: Whether to recurse into subdirectories.
            include_hidden: Whether to include hidden files.

        Returns:
            ScanResponse with file type counts.
        """
        response = await self._client.post(
            self._url("/organize/scan"),
            json={
                "input_dir": input_dir,
                "recursive": recursive,
                "include_hidden": include_hidden,
            },
        )
        self._raise_for_status(response)
        return ScanResponse.model_validate(response.json())

    async def preview_organize(
        self,
        input_dir: str,
        output_dir: str,
        *,
        options: OrganizationOptionsPayload | None = None,
        plan: OrganizationPlanPayload | None = None,
        skip_existing: bool | None = None,
        use_hardlinks: bool | None = None,
    ) -> OrganizationResultResponse:
        """Preview an organization without moving files.

        Args:
            input_dir: Source directory.
            output_dir: Destination directory.
            options: Complete canonical behavior options.
            plan: Optional reviewed executable plan.
            skip_existing: Skip files that already exist at the destination.
            use_hardlinks: Use hard links instead of copies.

        Returns:
            OrganizationResultResponse with the preview result.
        """
        payload = organization_request_payload(
            input_dir,
            output_dir,
            options=options,
            plan=plan,
            dry_run=True,
            run_in_background=False,
            skip_existing=skip_existing,
            use_hardlinks=use_hardlinks,
        )
        response = await self._client.post(
            self._url("/organize/preview"),
            json=payload,
        )
        self._raise_for_status(response)
        return OrganizationResultResponse.model_validate(response.json())

    async def organize(
        self,
        input_dir: str,
        output_dir: str,
        *,
        dry_run: bool = False,
        options: OrganizationOptionsPayload | None = None,
        plan: OrganizationPlanPayload | None = None,
        skip_existing: bool | None = None,
        use_hardlinks: bool | None = None,
        run_in_background: bool = True,
        idempotency_key: str | None = None,
    ) -> OrganizeExecuteResponse:
        """Execute file organization.

        When ``run_in_background`` is True (default), returns immediately with
        a ``job_id`` that can be polled via ``get_job()``.

        Args:
            input_dir: Source directory.
            output_dir: Destination directory.
            dry_run: Preview only, do not move files.
            options: Complete canonical behavior options.
            plan: Optional reviewed executable plan.
            skip_existing: Skip already-organized files.
            use_hardlinks: Use hard links instead of copies.
            run_in_background: Queue as a background job.
            idempotency_key: Optional key that deduplicates background submissions.

        Returns:
            OrganizeExecuteResponse with status and optional job_id.
        """
        payload = organization_request_payload(
            input_dir,
            output_dir,
            options=options,
            plan=plan,
            dry_run=dry_run,
            run_in_background=run_in_background,
            skip_existing=skip_existing,
            use_hardlinks=use_hardlinks,
            idempotency_key=idempotency_key,
        )
        response = await self._client.post(
            self._url("/organize/execute"),
            json=payload,
        )
        self._raise_for_status(response)
        return OrganizeExecuteResponse.model_validate(response.json())

    async def get_job(self, job_id: str) -> JobStatusResponse:
        """Get the status of a background organization job.

        Args:
            job_id: The job identifier returned by ``organize()``.

        Returns:
            JobStatusResponse with current status.
        """
        response = await self._client.get(self._url(f"/organize/status/{job_id}"))
        self._raise_for_status(response)
        return JobStatusResponse.model_validate(response.json())

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[JobStatusResponse]:
        """List recent organization jobs."""
        params: dict[str, str | int] = {"limit": limit}
        if status is not None:
            params["status"] = status
        rows = await self._request_list("GET", "/organize/jobs", params=params)
        return [JobStatusResponse.model_validate(row) for row in rows]

    async def cancel_job(
        self,
        job_id: str,
        *,
        expected_revision: int | None = None,
    ) -> JobStatusResponse:
        """Cancel a queued or scheduled organization job."""
        data = await self._request_json(
            "POST",
            f"/organize/jobs/{job_id}/cancel",
            json={"expected_revision": expected_revision},
        )
        return JobStatusResponse.model_validate(data)

    async def rollback_job(
        self,
        job_id: str,
        *,
        expected_revision: int | None = None,
    ) -> JobStatusResponse:
        """Rollback a completed organization job."""
        data = await self._request_json(
            "POST",
            f"/organize/jobs/{job_id}/rollback",
            json={"expected_revision": expected_revision},
        )
        return JobStatusResponse.model_validate(data)

    # -- system --------------------------------------------------------------

    async def system_status(self, path: str = ".") -> SystemStatusResponse:
        """Get system status including disk usage.

        Args:
            path: Path for disk usage calculation.

        Returns:
            SystemStatusResponse with system information.
        """
        response = await self._client.get(self._url("/system/status"), params={"path": path})
        self._raise_for_status(response)
        return SystemStatusResponse.model_validate(response.json())

    async def get_config(self, profile: str = "default") -> ConfigResponse:
        """Get application configuration.

        Args:
            profile: Configuration profile name.

        Returns:
            ConfigResponse with the configuration data.
        """
        response = await self._client.get(self._url("/system/config"), params={"profile": profile})
        self._raise_for_status(response)
        return ConfigResponse.model_validate(response.json())

    async def update_config(self, payload: dict[str, Any]) -> ConfigResponse:
        """Patch application configuration.

        Args:
            payload: Partial config update payload accepted by ``/system/config``.

        Returns:
            ConfigResponse with the updated configuration.
        """
        response = await self._client.patch(self._url("/system/config"), json=payload)
        self._raise_for_status(response)
        return ConfigResponse.model_validate(response.json())

    async def system_stats(
        self,
        *,
        path: str = ".",
        max_depth: int | None = None,
        use_cache: bool = True,
    ) -> StorageStatsResponse:
        """Get storage analytics statistics for a directory.

        Args:
            path: Directory path to analyze.
            max_depth: Optional directory depth limit.
            use_cache: Whether server-side cache should be used.
        """
        params: dict[str, Any] = {"path": path, "use_cache": use_cache}
        if max_depth is not None:
            params["max_depth"] = max_depth
        response = await self._client.get(self._url("/system/stats"), params=params)
        self._raise_for_status(response)
        return StorageStatsResponse.model_validate(response.json())

    # -- dedupe --------------------------------------------------------------

    async def dedupe_scan(
        self,
        path: str,
        *,
        recursive: bool = True,
        algorithm: str = "sha256",
        min_file_size: int = 0,
        max_file_size: int | None = None,
    ) -> DedupeScanResponse:
        """Scan a directory for duplicate files.

        Args:
            path: Directory to scan.
            recursive: Whether to recurse into subdirectories.
            algorithm: Hash algorithm (md5 or sha256).
            min_file_size: Minimum file size to consider.
            max_file_size: Maximum file size to consider.

        Returns:
            DedupeScanResponse with duplicate groups.
        """
        payload: dict[str, Any] = {
            "path": path,
            "recursive": recursive,
            "algorithm": algorithm,
            "min_file_size": min_file_size,
        }
        if max_file_size is not None:
            payload["max_file_size"] = max_file_size
        response = await self._client.post(self._url("/dedupe/scan"), json=payload)
        self._raise_for_status(response)
        return DedupeScanResponse.model_validate(response.json())

    async def dedupe_preview(
        self,
        path: str,
        *,
        recursive: bool = True,
        algorithm: str = "sha256",
    ) -> DedupePreviewResponse:
        """Preview which duplicates would be removed.

        Args:
            path: Directory to scan.
            recursive: Whether to recurse into subdirectories.
            algorithm: Hash algorithm (md5 or sha256).

        Returns:
            DedupePreviewResponse with keep/remove decisions.
        """
        response = await self._client.post(
            self._url("/dedupe/preview"),
            json={
                "path": path,
                "recursive": recursive,
                "algorithm": algorithm,
            },
        )
        self._raise_for_status(response)
        return DedupePreviewResponse.model_validate(response.json())

    async def dedupe_execute(
        self,
        path: str,
        *,
        recursive: bool = True,
        algorithm: str = "sha256",
        dry_run: bool = True,
        trash: bool = True,
    ) -> DedupeExecuteResponse:
        """Execute deduplication on a directory.

        Args:
            path: Directory to deduplicate.
            recursive: Whether to recurse into subdirectories.
            algorithm: Hash algorithm (md5 or sha256).
            dry_run: Preview only, do not remove files.
            trash: Move duplicates to trash instead of deleting permanently.

        Returns:
            DedupeExecuteResponse with the list of removed files.
        """
        response = await self._client.post(
            self._url("/dedupe/execute"),
            json={
                "path": path,
                "recursive": recursive,
                "algorithm": algorithm,
                "dry_run": dry_run,
                "trash": trash,
            },
        )
        self._raise_for_status(response)
        return DedupeExecuteResponse.model_validate(response.json())

    # -- extended public API ------------------------------------------------

    async def analyze(self, content: str) -> dict[str, Any]:
        """Analyze text content with the configured model."""
        return await self._request_json("POST", "/analyze", params={"content": content})

    async def search(
        self,
        query: str,
        *,
        file_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        path: str | None = None,
        semantic: bool = False,
    ) -> list[dict[str, Any]]:
        """Search indexed files with keyword or semantic retrieval."""
        params: dict[str, str | int | bool] = {"q": query, "semantic": semantic}
        if file_type is not None:
            params["type"] = file_type
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        if path is not None:
            params["path"] = path
        return cast(
            list[dict[str, Any]],
            await self._request_list("GET", "/search", params=params),
        )

    async def get_application_config(self, profile: str = "default") -> ConfigResponse:
        """Get a persisted application configuration profile."""
        data = await self._request_json("GET", "/config", params={"profile": profile})
        return ConfigResponse.model_validate(data)

    async def update_application_config(self, payload: dict[str, Any]) -> ConfigResponse:
        """Replace fields in a persisted application configuration profile."""
        data = await self._request_json("PUT", "/config", json=payload)
        return ConfigResponse.model_validate(data)

    async def reset_application_config(self, profile: str = "default") -> ConfigResponse:
        """Reset a persisted application configuration profile."""
        data = await self._request_json("POST", "/config/reset", params={"profile": profile})
        return ConfigResponse.model_validate(data)

    async def get_file_by_id(self, file_id: str) -> FileInfo:
        """Get file metadata by server identifier."""
        return FileInfo.model_validate(await self._request_json("GET", f"/files/{file_id}"))

    async def delete_file_by_id(
        self, file_id: str, *, permanent: bool = False
    ) -> DeleteFileResponse:
        """Delete or trash a file by server identifier."""
        data = await self._request_json(
            "DELETE", f"/files/{file_id}", params={"permanent": permanent}
        )
        return DeleteFileResponse.model_validate(data)

    async def upload_files(self, files: list[tuple[str, bytes]]) -> Any:
        """Upload one or more in-memory files."""
        multipart = [("files", (name, content)) for name, content in files]
        return await self._request_json("POST", "/files/upload", files=multipart)

    async def suggest_organization(
        self, filename: str, *, folder_suggestion: str | None = None
    ) -> dict[str, Any]:
        """Request the lightweight single-file organization suggestion."""
        return await self._request_json(
            "POST",
            "/organize",
            json={"filename": filename, "folder_suggestion": folder_suggestion},
        )

    async def toggle_daemon(self) -> dict[str, Any]:
        """Toggle the background daemon."""
        return await self._request_json("POST", "/daemon/toggle")

    async def start_daemon(self) -> dict[str, Any]:
        """Start the background daemon."""
        return await self._request_json("POST", "/daemon/start")

    async def stop_daemon(self) -> dict[str, Any]:
        """Stop the background daemon."""
        return await self._request_json("POST", "/daemon/stop")

    async def daemon_status(self) -> dict[str, Any]:
        """Get background daemon status."""
        return await self._request_json("GET", "/daemon/status")

    async def list_integrations(self) -> dict[str, Any]:
        """List configured integrations."""
        return await self._request_json("GET", "/integrations")

    async def update_integration_settings(
        self, integration_name: str, settings: dict[str, Any]
    ) -> dict[str, Any]:
        """Update one integration's settings."""
        return await self._request_json(
            "POST",
            f"/integrations/{integration_name}/settings",
            json={"settings": settings},
        )

    async def connect_integration(self, integration_name: str) -> dict[str, Any]:
        """Connect an integration."""
        return await self._request_json("POST", f"/integrations/{integration_name}/connect")

    async def disconnect_integration(self, integration_name: str) -> dict[str, Any]:
        """Disconnect an integration."""
        return await self._request_json("POST", f"/integrations/{integration_name}/disconnect")

    async def send_to_integration(
        self, integration_name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a file through an integration."""
        return await self._request_json(
            "POST", f"/integrations/{integration_name}/send", json=payload
        )

    async def get_browser_integration_config(self) -> dict[str, Any]:
        """Get browser-extension integration configuration."""
        return await self._request_json("GET", "/integrations/browser/config")

    async def issue_browser_integration_token(self, extension_id: str) -> dict[str, Any]:
        """Issue a browser-extension integration token."""
        return await self._request_json(
            "POST", "/integrations/browser/token", json={"extension_id": extension_id}
        )

    async def verify_browser_integration_token(self, token: str) -> dict[str, Any]:
        """Verify a browser-extension integration token."""
        return await self._request_json(
            "POST", "/integrations/browser/verify", json={"token": token}
        )

    async def list_marketplace_plugins(self, **params: Any) -> dict[str, Any]:
        """List marketplace plugins."""
        return await self._request_json("GET", "/marketplace/plugins", params=params)

    async def get_marketplace_plugin(self, name: str) -> dict[str, Any]:
        """Get one marketplace plugin."""
        return await self._request_json("GET", f"/marketplace/plugins/{name}")

    async def list_installed_plugins(self) -> list[dict[str, Any]]:
        """List installed marketplace plugins."""
        return cast(
            list[dict[str, Any]],
            await self._request_list("GET", "/marketplace/installed"),
        )

    async def list_marketplace_updates(self) -> list[str]:
        """List plugins with available updates."""
        return cast(list[str], await self._request_list("GET", "/marketplace/updates"))

    async def install_marketplace_plugin(
        self, name: str, *, version: str | None = None
    ) -> dict[str, Any]:
        """Install a marketplace plugin."""
        params = {"version": version} if version is not None else {}
        return await self._request_json(
            "POST", f"/marketplace/plugins/{name}/install", params=params
        )

    async def uninstall_marketplace_plugin(self, name: str) -> Any:
        """Uninstall a marketplace plugin."""
        return await self._request_json("DELETE", f"/marketplace/plugins/{name}")

    async def update_marketplace_plugin(self, name: str) -> dict[str, Any]:
        """Update a marketplace plugin."""
        return await self._request_json("POST", f"/marketplace/plugins/{name}/update")

    async def list_marketplace_reviews(self, name: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """List reviews for a marketplace plugin."""
        return cast(
            list[dict[str, Any]],
            await self._request_list(
                "GET", f"/marketplace/plugins/{name}/reviews", params={"limit": limit}
            ),
        )

    async def add_marketplace_review(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Add a marketplace plugin review."""
        return await self._request_json(
            "POST", f"/marketplace/plugins/{name}/reviews", json=payload
        )

    async def get_setup_status(self) -> dict[str, Any]:
        """Get initial setup status."""
        return await self._request_json("GET", "/setup/status")

    async def detect_setup_capabilities(self) -> dict[str, Any]:
        """Detect local setup capabilities."""
        return await self._request_json("GET", "/setup/capabilities")

    async def complete_setup(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist setup selections."""
        return await self._request_json("POST", "/setup/complete", json=payload)

    async def browse_setup_folder(self) -> dict[str, Any]:
        """Browse a local folder during setup."""
        return await self._request_json("GET", "/setup/browse-folder")

    async def list_plugin_files(
        self,
        path: str,
        *,
        recursive: bool = False,
        include_hidden: bool = False,
        max_items: int = 200,
    ) -> dict[str, Any]:
        """List files through the plugin runtime API."""
        return await self._request_json(
            "GET",
            "/plugins/files/list",
            params={
                "path": path,
                "recursive": recursive,
                "include_hidden": include_hidden,
                "max_items": max_items,
            },
        )

    async def get_plugin_file_metadata(self, path: str) -> dict[str, Any]:
        """Get file metadata through the plugin runtime API."""
        return await self._request_json("GET", "/plugins/files/metadata", params={"path": path})

    async def organize_plugin_file(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Organize one file through the plugin runtime API."""
        return await self._request_json("POST", "/plugins/files/organize", json=payload)

    async def get_plugin_config(self, key: str, *, profile: str = "default") -> dict[str, Any]:
        """Read a plugin configuration value."""
        return await self._request_json(
            "GET", "/plugins/config/get", params={"key": key, "profile": profile}
        )

    async def register_plugin_hook(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Register a plugin hook."""
        return await self._request_json("POST", "/plugins/hooks/register", json=payload)

    async def unregister_plugin_hook(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Unregister a plugin hook."""
        return await self._request_json("POST", "/plugins/hooks/unregister", json=payload)

    async def list_plugin_hooks(self, event: str | None = None) -> dict[str, Any]:
        """List plugin hooks."""
        params = {"event": event} if event is not None else {}
        return await self._request_json("GET", "/plugins/hooks", params=params)

    async def trigger_plugin_hook(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Trigger a plugin hook event."""
        return await self._request_json("POST", "/plugins/hooks/trigger", json=payload)

    # -- context manager -----------------------------------------------------

    async def __aenter__(self) -> AsyncFileOrganizerClient:
        """Enter the async context manager."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit the async context manager and close the client."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying async HTTP client."""
        await self._client.aclose()
