/// Splash screen module — registers the Tauri command for sidecar state queries.
///
/// The splash screen HTML polls this command on load to handle the case where
/// the `sidecar-state` event was emitted before the webview finished initialising.

use tauri::Manager;

/// Returns the current sidecar state for the splash screen.
///
/// Queries the actual `SidecarManager` instance stored in Tauri managed state.
/// Falls back to `"starting"` only if the manager is not yet registered.
/// Returns `"error"` if state access or mutex lock fails, so the splash
/// screen can display an error instead of polling forever.
#[tauri::command]
pub fn get_sidecar_state(app: tauri::AppHandle) -> serde_json::Value {
    let Some(mgr) = app.try_state::<std::sync::Mutex<crate::SidecarManager>>() else {
        // State not yet registered — the sidecar manager hasn't been
        // initialised by the Tauri setup hook. This is expected during
        // early startup; the splash screen should keep polling.
        return serde_json::json!({
            "state": "starting",
            "port": 0,
            "message": "Sidecar manager not yet initialised"
        });
    };

    // Bind the match result to a local variable so that the `MutexGuard`
    // temporary is dropped before `mgr`, avoiding a lifetime error.
    let result = match mgr.lock() {
        Ok(sidecar) => {
            let state_str = match sidecar.state() {
                crate::sidecar::SidecarState::Stopped => "stopped",
                crate::sidecar::SidecarState::Starting => "starting",
                crate::sidecar::SidecarState::Ready => "ready",
                crate::sidecar::SidecarState::Crashed => "unhealthy",
            };
            serde_json::json!({
                "state": state_str,
                "port": sidecar.port(),
                "message": null
            })
        }
        Err(e) => {
            // Mutex is poisoned — a thread panicked while holding the lock.
            // This is a fatal internal error; report it so the splash screen
            // can show an error message instead of looping indefinitely.
            serde_json::json!({
                "state": "error",
                "port": 0,
                "message": format!("Internal error: failed to acquire sidecar lock: {}", e)
            })
        }
    };
    result
}
