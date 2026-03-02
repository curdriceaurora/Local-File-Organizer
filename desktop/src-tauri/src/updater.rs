//! Tauri shell updater module.
//!
//! Uses `tauri-plugin-updater` to check for and install updates to the
//! Tauri shell binary. Emits events to the frontend during the update
//! lifecycle so the UI can show progress to the user.

use serde::Serialize;
use tauri::{AppHandle, Emitter};
use tauri_plugin_updater::UpdaterExt;

// ---------------------------------------------------------------------------
// Event payloads
// ---------------------------------------------------------------------------

/// Payload for the `update-available` event.
#[derive(Debug, Clone, Serialize)]
pub struct UpdateAvailablePayload {
    pub version: String,
    pub notes: Option<String>,
    pub pub_date: Option<String>,
}

/// Payload for download-progress events.
#[derive(Debug, Clone, Serialize)]
pub struct DownloadProgressPayload {
    /// Bytes downloaded so far.
    pub downloaded: u64,
    /// Total content length, if known.
    pub total: Option<u64>,
}

/// Payload for `update-failed` events.
#[derive(Debug, Clone, Serialize)]
pub struct UpdateFailedPayload {
    pub reason: String,
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// Check whether a shell update is available.
///
/// Queries the GitHub Releases endpoint configured in `tauri.conf.json`.
/// Emits `update-available` to the frontend when a newer version exists, or
/// returns `Ok(false)` when the shell is already up to date.
///
/// # Errors
///
/// Returns an error string if the updater plugin cannot reach the endpoint.
#[tauri::command]
pub async fn check_for_updates(app: AppHandle) -> Result<bool, String> {
    let updater = app
        .updater()
        .map_err(|e| format!("Updater unavailable: {e}"))?;

    match updater.check().await {
        Ok(Some(update)) => {
            let payload = UpdateAvailablePayload {
                version: update.version.clone(),
                notes: update.body.clone(),
                pub_date: update.date.map(|d| d.to_string()),
            };
            app.emit("update-available", payload)
                .map_err(|e| format!("Failed to emit event: {e}"))?;
            Ok(true)
        }
        Ok(None) => Ok(false),
        Err(e) => Err(format!("Update check failed: {e}")),
    }
}

/// Download and install a pending shell update.
///
/// This function re-checks for an update so that the caller does not need to
/// hold on to a previous `Update` handle. Progress is reported via
/// `update-downloading` events (with byte counts) and a final
/// `update-installed` or `update-failed` event.
///
/// The application is restarted automatically after a successful install.
///
/// # Errors
///
/// Returns an error string if no update is available, the download fails, or
/// SHA-256 verification fails.
#[tauri::command]
pub async fn install_update(app: AppHandle) -> Result<(), String> {
    let updater = app
        .updater()
        .map_err(|e| format!("Updater unavailable: {e}"))?;

    let update = updater
        .check()
        .await
        .map_err(|e| format!("Update check failed: {e}"))?
        .ok_or_else(|| "No update available".to_string())?;

    let version = update.version.clone();
    let app_for_progress = app.clone();

    let result = update
        .download_and_install(
            move |downloaded, total| {
                let payload = DownloadProgressPayload { downloaded: downloaded as u64, total };
                // Best-effort emit; ignore send errors during progress.
                let _ = app_for_progress.emit("update-downloading", payload);
            },
            || {},
        )
        .await;

    match result {
        Ok(()) => {
            app.emit("update-installed", version)
                .map_err(|e| format!("Failed to emit event: {e}"))?;
            // Restart is handled by the plugin automatically.
            Ok(())
        }
        Err(e) => {
            let reason = format!("Install failed: {e}");
            let _ = app.emit(
                "update-failed",
                UpdateFailedPayload {
                    reason: reason.clone(),
                },
            );
            Err(reason)
        }
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------------
    // Payload serialization tests (pure, no AppHandle required)
    // -----------------------------------------------------------------------

    #[test]
    fn update_available_payload_serializes_correctly() {
        let payload = UpdateAvailablePayload {
            version: "2.1.0".to_string(),
            notes: Some("Bug fixes and performance improvements.".to_string()),
            pub_date: Some("2026-03-01T00:00:00Z".to_string()),
        };
        let json = serde_json::to_string(&payload).expect("serialization failed");
        assert!(json.contains("\"version\":\"2.1.0\""));
        assert!(json.contains("\"notes\""));
        assert!(json.contains("\"pub_date\""));
    }

    #[test]
    fn update_available_payload_handles_optional_fields() {
        let payload = UpdateAvailablePayload {
            version: "3.0.0".to_string(),
            notes: None,
            pub_date: None,
        };
        let json = serde_json::to_string(&payload).expect("serialization failed");
        assert!(json.contains("\"version\":\"3.0.0\""));
        assert!(json.contains("\"notes\":null"));
        assert!(json.contains("\"pub_date\":null"));
    }

    #[test]
    fn download_progress_payload_serializes_correctly() {
        let payload = DownloadProgressPayload {
            downloaded: 1024,
            total: Some(4096),
        };
        let json = serde_json::to_string(&payload).expect("serialization failed");
        assert!(json.contains("\"downloaded\":1024"));
        assert!(json.contains("\"total\":4096"));
    }

    #[test]
    fn download_progress_payload_handles_unknown_total() {
        let payload = DownloadProgressPayload {
            downloaded: 512,
            total: None,
        };
        let json = serde_json::to_string(&payload).expect("serialization failed");
        assert!(json.contains("\"downloaded\":512"));
        assert!(json.contains("\"total\":null"));
    }

    #[test]
    fn update_failed_payload_serializes_correctly() {
        let payload = UpdateFailedPayload {
            reason: "SHA-256 mismatch".to_string(),
        };
        let json = serde_json::to_string(&payload).expect("serialization failed");
        assert!(json.contains("SHA-256 mismatch"));
    }

    #[test]
    fn version_string_roundtrip() {
        // Ensure version strings survive a JSON roundtrip without mutation.
        let original = "2.0.0-alpha.1";
        let payload = UpdateAvailablePayload {
            version: original.to_string(),
            notes: None,
            pub_date: None,
        };
        let json = serde_json::to_string(&payload).unwrap();
        let recovered: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(recovered["version"].as_str().unwrap(), original);
    }
}
