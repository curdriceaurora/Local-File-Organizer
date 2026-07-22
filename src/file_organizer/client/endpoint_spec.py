"""Shared inventory for public REST operations and official SDK methods."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClientEndpoint:
    """Map one public HTTP operation to equivalent SDK entry points."""

    method: str
    path: str
    capability_ids: tuple[str, ...]
    python_method: str
    typescript_method: str

    @property
    def key(self) -> str:
        """Return the normalized HTTP inventory key."""
        return f"{self.method} {self.path}"


def _endpoint(
    method: str,
    path: str,
    capability: str,
    python_method: str,
    typescript_method: str,
    *additional_capabilities: str,
) -> ClientEndpoint:
    return ClientEndpoint(
        method,
        path,
        (capability, *additional_capabilities),
        python_method,
        typescript_method,
    )


PUBLIC_ENDPOINTS: tuple[ClientEndpoint, ...] = (
    _endpoint(
        "POST",
        "/api/v1/analyze",
        "analysis.inspect",
        "analyze",
        "analyze",
        "audio.transcribe",
        "video.analyze",
    ),
    _endpoint("POST", "/api/v1/auth/register", "authentication.manage", "register", "register"),
    _endpoint("POST", "/api/v1/auth/login", "authentication.manage", "login", "login"),
    _endpoint(
        "POST", "/api/v1/auth/refresh", "authentication.manage", "refresh_token", "refreshToken"
    ),
    _endpoint("POST", "/api/v1/auth/logout", "authentication.manage", "logout", "logout"),
    _endpoint("GET", "/api/v1/auth/me", "authentication.manage", "me", "me"),
    _endpoint(
        "GET",
        "/api/v1/config",
        "configuration.manage",
        "get_application_config",
        "getApplicationConfig",
        "methodology.configure",
    ),
    _endpoint(
        "PUT",
        "/api/v1/config",
        "configuration.manage",
        "update_application_config",
        "updateApplicationConfig",
        "methodology.configure",
    ),
    _endpoint(
        "POST",
        "/api/v1/config/reset",
        "configuration.manage",
        "reset_application_config",
        "resetApplicationConfig",
    ),
    _endpoint(
        "POST", "/api/v1/daemon/toggle", "automation.watcher", "toggle_daemon", "toggleDaemon"
    ),
    _endpoint("POST", "/api/v1/daemon/start", "automation.watcher", "start_daemon", "startDaemon"),
    _endpoint("POST", "/api/v1/daemon/stop", "automation.watcher", "stop_daemon", "stopDaemon"),
    _endpoint(
        "GET", "/api/v1/daemon/status", "automation.watcher", "daemon_status", "daemonStatus"
    ),
    _endpoint("POST", "/api/v1/dedupe/scan", "deduplication.manage", "dedupe_scan", "dedupeScan"),
    _endpoint(
        "POST", "/api/v1/dedupe/preview", "deduplication.manage", "dedupe_preview", "dedupePreview"
    ),
    _endpoint(
        "POST", "/api/v1/dedupe/execute", "deduplication.manage", "dedupe_execute", "dedupeExecute"
    ),
    _endpoint("GET", "/api/v1/files", "files.browse", "list_files", "listFiles"),
    _endpoint("GET", "/api/v1/files/info", "files.inspect", "get_file_info", "getFileInfo"),
    _endpoint(
        "GET", "/api/v1/files/content", "files.inspect", "read_file_content", "readFileContent"
    ),
    _endpoint("GET", "/api/v1/files/{file_id}", "files.inspect", "get_file_by_id", "getFileById"),
    _endpoint("POST", "/api/v1/files/move", "files.mutate", "move_file", "moveFile"),
    _endpoint("DELETE", "/api/v1/files", "files.mutate", "delete_file", "deleteFile"),
    _endpoint(
        "DELETE", "/api/v1/files/{file_id}", "files.mutate", "delete_file_by_id", "deleteFileById"
    ),
    _endpoint("POST", "/api/v1/files/upload", "files.mutate", "upload_files", "uploadFiles"),
    _endpoint("GET", "/api/v1/health", "system.inspect", "health", "health"),
    _endpoint(
        "GET",
        "/api/v1/integrations",
        "integrations.manage",
        "list_integrations",
        "listIntegrations",
    ),
    _endpoint(
        "POST",
        "/api/v1/integrations/{integration_name}/settings",
        "integrations.manage",
        "update_integration_settings",
        "updateIntegrationSettings",
    ),
    _endpoint(
        "POST",
        "/api/v1/integrations/{integration_name}/connect",
        "integrations.manage",
        "connect_integration",
        "connectIntegration",
    ),
    _endpoint(
        "POST",
        "/api/v1/integrations/{integration_name}/disconnect",
        "integrations.manage",
        "disconnect_integration",
        "disconnectIntegration",
    ),
    _endpoint(
        "POST",
        "/api/v1/integrations/{integration_name}/send",
        "integrations.manage",
        "send_to_integration",
        "sendToIntegration",
    ),
    _endpoint(
        "GET",
        "/api/v1/integrations/browser/config",
        "integrations.manage",
        "get_browser_integration_config",
        "getBrowserIntegrationConfig",
    ),
    _endpoint(
        "POST",
        "/api/v1/integrations/browser/token",
        "integrations.manage",
        "issue_browser_integration_token",
        "issueBrowserIntegrationToken",
    ),
    _endpoint(
        "POST",
        "/api/v1/integrations/browser/verify",
        "integrations.manage",
        "verify_browser_integration_token",
        "verifyBrowserIntegrationToken",
    ),
    _endpoint(
        "GET",
        "/api/v1/marketplace/plugins",
        "marketplace.manage",
        "list_marketplace_plugins",
        "listMarketplacePlugins",
    ),
    _endpoint(
        "GET",
        "/api/v1/marketplace/plugins/{name}",
        "marketplace.manage",
        "get_marketplace_plugin",
        "getMarketplacePlugin",
    ),
    _endpoint(
        "GET",
        "/api/v1/marketplace/installed",
        "marketplace.manage",
        "list_installed_plugins",
        "listInstalledPlugins",
    ),
    _endpoint(
        "GET",
        "/api/v1/marketplace/updates",
        "marketplace.manage",
        "list_marketplace_updates",
        "listMarketplaceUpdates",
    ),
    _endpoint(
        "POST",
        "/api/v1/marketplace/plugins/{name}/install",
        "marketplace.manage",
        "install_marketplace_plugin",
        "installMarketplacePlugin",
    ),
    _endpoint(
        "DELETE",
        "/api/v1/marketplace/plugins/{name}",
        "marketplace.manage",
        "uninstall_marketplace_plugin",
        "uninstallMarketplacePlugin",
    ),
    _endpoint(
        "POST",
        "/api/v1/marketplace/plugins/{name}/update",
        "marketplace.manage",
        "update_marketplace_plugin",
        "updateMarketplacePlugin",
    ),
    _endpoint(
        "GET",
        "/api/v1/marketplace/plugins/{name}/reviews",
        "marketplace.manage",
        "list_marketplace_reviews",
        "listMarketplaceReviews",
    ),
    _endpoint(
        "POST",
        "/api/v1/marketplace/plugins/{name}/reviews",
        "marketplace.manage",
        "add_marketplace_review",
        "addMarketplaceReview",
    ),
    _endpoint("POST", "/api/v1/organize/scan", "organization.scan", "scan", "scan"),
    _endpoint(
        "POST",
        "/api/v1/organize/preview",
        "organization.preview",
        "preview_organize",
        "previewOrganize",
    ),
    _endpoint("POST", "/api/v1/organize/execute", "organization.execute", "organize", "organize"),
    _endpoint(
        "GET", "/api/v1/organize/status/{job_id}", "organization.jobs-recovery", "get_job", "getJob"
    ),
    _endpoint(
        "GET",
        "/api/v1/organize/jobs",
        "organization.jobs-recovery",
        "list_jobs",
        "listJobs",
    ),
    _endpoint(
        "POST",
        "/api/v1/organize/jobs/{job_id}/cancel",
        "organization.jobs-recovery",
        "cancel_job",
        "cancelJob",
    ),
    _endpoint(
        "POST",
        "/api/v1/organize/jobs/{job_id}/rollback",
        "organization.jobs-recovery",
        "rollback_job",
        "rollbackJob",
    ),
    _endpoint(
        "POST",
        "/api/v1/organize",
        "organization.execute",
        "suggest_organization",
        "suggestOrganization",
    ),
    _endpoint("GET", "/api/v1/search", "search.query", "search", "search"),
    _endpoint(
        "GET", "/api/v1/setup/status", "setup.configure", "get_setup_status", "getSetupStatus"
    ),
    _endpoint(
        "GET",
        "/api/v1/setup/capabilities",
        "setup.configure",
        "detect_setup_capabilities",
        "detectSetupCapabilities",
    ),
    _endpoint(
        "POST", "/api/v1/setup/complete", "setup.configure", "complete_setup", "completeSetup"
    ),
    _endpoint(
        "GET",
        "/api/v1/setup/browse-folder",
        "setup.configure",
        "browse_setup_folder",
        "browseSetupFolder",
    ),
    _endpoint("GET", "/api/v1/system/status", "system.inspect", "system_status", "systemStatus"),
    _endpoint("GET", "/api/v1/system/config", "configuration.manage", "get_config", "getConfig"),
    _endpoint(
        "PATCH", "/api/v1/system/config", "configuration.manage", "update_config", "updateConfig"
    ),
    _endpoint(
        "GET",
        "/api/v1/system/stats",
        "analytics.inspect",
        "system_stats",
        "systemStats",
        "system.inspect",
    ),
    _endpoint(
        "GET",
        "/api/v1/plugins/files/list",
        "plugins.runtime",
        "list_plugin_files",
        "listPluginFiles",
    ),
    _endpoint(
        "GET",
        "/api/v1/plugins/files/metadata",
        "plugins.runtime",
        "get_plugin_file_metadata",
        "getPluginFileMetadata",
    ),
    _endpoint(
        "POST",
        "/api/v1/plugins/files/organize",
        "plugins.runtime",
        "organize_plugin_file",
        "organizePluginFile",
    ),
    _endpoint(
        "GET",
        "/api/v1/plugins/config/get",
        "plugins.runtime",
        "get_plugin_config",
        "getPluginConfig",
    ),
    _endpoint(
        "POST",
        "/api/v1/plugins/hooks/register",
        "plugins.runtime",
        "register_plugin_hook",
        "registerPluginHook",
    ),
    _endpoint(
        "POST",
        "/api/v1/plugins/hooks/unregister",
        "plugins.runtime",
        "unregister_plugin_hook",
        "unregisterPluginHook",
    ),
    _endpoint(
        "GET", "/api/v1/plugins/hooks", "plugins.runtime", "list_plugin_hooks", "listPluginHooks"
    ),
    _endpoint(
        "POST",
        "/api/v1/plugins/hooks/trigger",
        "plugins.runtime",
        "trigger_plugin_hook",
        "triggerPluginHook",
    ),
)


# WebSocket operations are not representable in OpenAPI. The HTTP SDKs expose
# job polling; native event-stream clients remain explicitly outside this slice.
INTENTIONAL_EXCLUSIONS: dict[str, str] = {
    "WS /api/v1/ws/{client_id}": (
        "WebSocket transport is not described by OpenAPI; use job polling until "
        "a separately versioned realtime SDK contract is introduced."
    )
}
