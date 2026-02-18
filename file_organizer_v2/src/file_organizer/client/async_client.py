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

from typing import Any, Optional

import httpx

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
        api_key: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
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
        message = f"HTTP {status}: {detail}"

        if status in (401, 403):
            raise AuthenticationError(message, status_code=status, detail=str(detail))
        if status == 404:
            raise NotFoundError(message, status_code=status, detail=str(detail))
        if status == 422:
            raise ValidationError(message, status_code=status, detail=str(detail))
        if status >= 500:
            raise ServerError(message, status_code=status, detail=str(detail))
        raise ClientError(message, status_code=status, detail=str(detail))

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
        file_type: Optional[str] = None,
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
        skip_existing: bool = True,
        use_hardlinks: bool = True,
    ) -> OrganizationResultResponse:
        """Preview an organization without moving files.

        Args:
            input_dir: Source directory.
            output_dir: Destination directory.
            skip_existing: Skip files that already exist at the destination.
            use_hardlinks: Use hard links instead of copies.

        Returns:
            OrganizationResultResponse with the preview result.
        """
        response = await self._client.post(
            self._url("/organize/preview"),
            json={
                "input_dir": input_dir,
                "output_dir": output_dir,
                "skip_existing": skip_existing,
                "dry_run": True,
                "use_hardlinks": use_hardlinks,
                "run_in_background": False,
            },
        )
        self._raise_for_status(response)
        return OrganizationResultResponse.model_validate(response.json())

    async def organize(
        self,
        input_dir: str,
        output_dir: str,
        *,
        dry_run: bool = False,
        skip_existing: bool = True,
        use_hardlinks: bool = True,
        run_in_background: bool = True,
    ) -> OrganizeExecuteResponse:
        """Execute file organization.

        When ``run_in_background`` is True (default), returns immediately with
        a ``job_id`` that can be polled via ``get_job()``.

        Args:
            input_dir: Source directory.
            output_dir: Destination directory.
            dry_run: Preview only, do not move files.
            skip_existing: Skip already-organized files.
            use_hardlinks: Use hard links instead of copies.
            run_in_background: Queue as a background job.

        Returns:
            OrganizeExecuteResponse with status and optional job_id.
        """
        response = await self._client.post(
            self._url("/organize/execute"),
            json={
                "input_dir": input_dir,
                "output_dir": output_dir,
                "dry_run": dry_run,
                "skip_existing": skip_existing,
                "use_hardlinks": use_hardlinks,
                "run_in_background": run_in_background,
            },
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
        max_depth: Optional[int] = None,
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
        max_file_size: Optional[int] = None,
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

    # -- context manager -----------------------------------------------------

    async def __aenter__(self) -> AsyncFileOrganizerClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying async HTTP client."""
        await self._client.aclose()
