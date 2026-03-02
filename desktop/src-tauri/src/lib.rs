mod daemon;
mod notifications;
mod sidecar;
mod splash;
mod tray;
mod updater;

pub use sidecar::SidecarManager;

use std::path::PathBuf;
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            splash::get_sidecar_state,
            updater::check_for_updates,
            updater::install_update,
        ])
        .setup(|app| {
            // Resolve sidecar binary path relative to the app resource directory.
            let binary_name = format!(
                "file-organizer-backend-{}",
                env!("TARGET_TRIPLE")
            );
            let binary_path = app
                .path()
                .resource_dir()
                .map(|d| d.join("binaries").join(&binary_name))
                .unwrap_or_else(|_| PathBuf::from(&binary_name));

            // Start the sidecar and retrieve the dynamically assigned port.
            let sidecar = SidecarManager::new(binary_path, app.handle().clone())
                .expect("failed to create sidecar manager");
            let port = sidecar.port();

            if let Err(e) = sidecar.start() {
                eprintln!("Warning: sidecar start failed: {e}");
            }

            // Store the sidecar manager in Tauri managed state for later access.
            app.manage(std::sync::Mutex::new(sidecar));

            // Spawn a background thread that polls the health endpoint until the
            // sidecar is ready.  This bridges the gap between `start()` (which
            // only emits "starting") and the "ready" event the splash screen
            // waits for.
            let app_handle = app.handle().clone();
            std::thread::spawn(move || {
                let state = app_handle.state::<std::sync::Mutex<SidecarManager>>();
                // Lock briefly to call wait_until_ready which does its own
                // internal polling loop.  The lock is held for the duration of
                // health polling, which is acceptable at startup since no other
                // code path needs the sidecar manager until the UI is loaded.
                if let Ok(mgr) = state.lock() {
                    if let Err(e) = mgr.wait_until_ready() {
                        eprintln!("Warning: sidecar health poll failed: {e}");
                    }
                }; // Semicolon ensures MutexGuard temporary drops before `state`.
            });

            // Create tray with the dynamic sidecar port.
            // The returned handle must be kept alive; dropping it removes the
            // tray icon.  Storing it in Tauri managed state ties its lifetime
            // to the application.
            let tray_handle = tray::create_tray(&app.handle(), port)?;
            app.manage(tray_handle);
            notifications::register_notification_listeners(&app.handle());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
