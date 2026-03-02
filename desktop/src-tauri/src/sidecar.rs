use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::Emitter;

const MAX_RETRIES: u32 = 3;
const HEALTH_POLL_TIMEOUT_SECS: u64 = 30;
const SHUTDOWN_WAIT_SECS: u64 = 5;

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq)]
pub enum SidecarState {
    Stopped,
    Starting,
    Ready,
    Crashed,
}

// ---------------------------------------------------------------------------
// Event payload
// ---------------------------------------------------------------------------

/// Payload emitted on the `sidecar-state` Tauri event whenever the sidecar
/// process transitions between lifecycle states.
///
/// The frontend can listen with:
/// ```js
/// import { listen } from '@tauri-apps/api/event';
/// await listen('sidecar-state', (event) => console.log(event.payload));
/// ```
#[derive(Debug, Clone, Serialize)]
pub struct SidecarStatePayload {
    /// Current sidecar state: `"starting"`, `"ready"`, `"stopped"`, or `"unhealthy"`.
    pub state: &'static str,
    /// The TCP port the sidecar is listening on, or `None` when stopped/unhealthy.
    pub port: Option<u16>,
    /// Error description, populated only for `"unhealthy"` transitions.
    pub error: Option<String>,
    /// UTC Unix timestamp (seconds) at the moment of the transition.
    pub timestamp: u64,
}

// ---------------------------------------------------------------------------
// Manager
// ---------------------------------------------------------------------------

pub struct SidecarManager {
    binary_path: PathBuf,
    port: u16,
    state: Arc<Mutex<SidecarState>>,
    child: Arc<Mutex<Option<Child>>>,
    retry_count: Arc<Mutex<u32>>,
    /// Optional AppHandle used to emit `sidecar-state` events to the frontend.
    /// `None` only in unit-test contexts where no Tauri runtime is available.
    app_handle: Option<tauri::AppHandle>,
}

impl SidecarManager {
    pub fn new(binary_path: PathBuf, app: tauri::AppHandle) -> std::io::Result<Self> {
        let port = Self::find_available_port()?;
        Ok(Self {
            binary_path,
            port,
            state: Arc::new(Mutex::new(SidecarState::Stopped)),
            child: Arc::new(Mutex::new(None)),
            retry_count: Arc::new(Mutex::new(0)),
            app_handle: Some(app),
        })
    }

    /// Construct a manager with no AppHandle for unit tests.
    ///
    /// Events will not be emitted; all other behaviour is identical.
    #[cfg(test)]
    pub fn new_for_test(port: u16) -> Self {
        Self {
            binary_path: PathBuf::from("/usr/bin/file-organizer"),
            port,
            state: Arc::new(Mutex::new(SidecarState::Stopped)),
            child: Arc::new(Mutex::new(None)),
            retry_count: Arc::new(Mutex::new(0)),
            app_handle: None,
        }
    }

    /// Bind to port 0 and read the OS-assigned port.
    fn find_available_port() -> std::io::Result<u16> {
        let listener = TcpListener::bind("127.0.0.1:0")?;
        Ok(listener.local_addr()?.port())
    }

    pub fn port(&self) -> u16 {
        self.port
    }

    pub fn health_url(&self) -> String {
        format!("http://127.0.0.1:{}/api/v1/health", self.port)
    }

    /// Emit a `sidecar-state` event to all frontend windows.
    ///
    /// Silently no-ops when `app_handle` is `None` (test mode).
    fn emit_state(&self, payload: SidecarStatePayload) {
        if let Some(app) = &self.app_handle {
            let _ = app.emit("sidecar-state", payload);
        }
    }

    /// Returns the current UTC Unix timestamp in seconds.
    fn unix_ts() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs()
    }

    /// Spawn the sidecar binary with `serve --host 127.0.0.1 --port <port>` arguments.
    ///
    /// The CLI requires the `serve` subcommand. We bind to localhost only to
    /// prevent the API from being exposed on the local network.
    /// Transitions state to `Starting` and emits a `sidecar-state` event.
    pub fn start(&self) -> std::io::Result<()> {
        *self.state.lock().unwrap() = SidecarState::Starting;
        self.emit_state(SidecarStatePayload {
            state: "starting",
            port: Some(self.port),
            error: None,
            timestamp: Self::unix_ts(),
        });

        let child = Command::new(&self.binary_path)
            .arg("serve")
            .arg("--host")
            .arg("127.0.0.1")
            .arg("--port")
            .arg(self.port.to_string())
            .spawn()?;

        *self.child.lock().unwrap() = Some(child);
        Ok(())
    }

    /// Poll the health endpoint with exponential backoff until ready or timeout.
    ///
    /// Transitions to `Ready` on success (emitting `sidecar-state { state: "ready" }`) or
    /// to `Crashed` on timeout (emitting `sidecar-state { state: "unhealthy" }`).
    pub fn wait_until_ready(&self) -> Result<(), String> {
        let timeout = Duration::from_secs(HEALTH_POLL_TIMEOUT_SECS);
        let start = Instant::now();
        let mut delay_ms = 100u64;

        loop {
            if start.elapsed() > timeout {
                *self.state.lock().unwrap() = SidecarState::Crashed;
                let error_message = format!(
                    "Backend did not become ready within {}s",
                    HEALTH_POLL_TIMEOUT_SECS
                );
                self.emit_state(SidecarStatePayload {
                    state: "unhealthy",
                    port: None,
                    error: Some(error_message.clone()),
                    timestamp: Self::unix_ts(),
                });
                return Err(error_message);
            }

            if self.check_health() {
                *self.state.lock().unwrap() = SidecarState::Ready;
                self.emit_state(SidecarStatePayload {
                    state: "ready",
                    port: Some(self.port),
                    error: None,
                    timestamp: Self::unix_ts(),
                });
                return Ok(());
            }

            std::thread::sleep(Duration::from_millis(delay_ms));
            delay_ms = (delay_ms * 2).min(5000); // cap at 5 seconds
        }
    }

    /// Perform a minimal HTTP GET to the health endpoint and verify the JSON body.
    ///
    /// Returns `true` only when the server responds with HTTP 200 (or 207 for
    /// degraded) **and** the body contains `"status":"ok"` or `"status":"degraded"`.
    pub fn check_health(&self) -> bool {
        use std::io::{Read, Write};
        use std::net::{SocketAddr, TcpStream};

        let addr = format!("127.0.0.1:{}", self.port);
        let sock_addr: SocketAddr = match addr.parse() {
            Ok(a) => a,
            Err(_) => return false,
        };

        if let Ok(mut stream) = TcpStream::connect_timeout(&sock_addr, Duration::from_millis(500)) {
            stream.set_read_timeout(Some(Duration::from_secs(5))).ok();
            let request = format!(
                "GET /api/v1/health HTTP/1.0\r\nHost: 127.0.0.1:{}\r\n\r\n",
                self.port
            );
            if stream.write_all(request.as_bytes()).is_ok() {
                let mut response = String::new();
                let _ = stream.read_to_string(&mut response);

                let status_ok = response.starts_with("HTTP/1.0 200")
                    || response.starts_with("HTTP/1.1 200")
                    || response.starts_with("HTTP/1.0 207")
                    || response.starts_with("HTTP/1.1 207");
                if !status_ok {
                    return false;
                }

                // Verify the JSON body contains a valid health status.
                // The body follows the first "\r\n\r\n" separator.
                if let Some(body_start) = response.find("\r\n\r\n") {
                    let body = &response[body_start + 4..];
                    return body.contains("\"status\":\"ok\"")
                        || body.contains("\"status\": \"ok\"")
                        || body.contains("\"status\":\"degraded\"")
                        || body.contains("\"status\": \"degraded\"");
                }
                return false;
            }
        }
        false
    }

    /// Check whether the child process is still alive.
    ///
    /// If it has exited, attempt to restart it up to MAX_RETRIES times.
    /// Returns `true` if the sidecar is running (or successfully restarted),
    /// `false` if the maximum retry count has been exceeded.
    ///
    /// Emits `sidecar-state { state: "unhealthy" }` when retries are exhausted.
    pub fn monitor(&self) -> bool {
        // Check whether the child process is still running.
        {
            let mut child_guard = self.child.lock().unwrap();
            match child_guard.as_mut() {
                None => return false,
                Some(child) => match child.try_wait() {
                    Ok(Some(_)) => {}        // Process has exited — fall through to restart logic
                    Ok(None) => return true, // Still running
                    Err(_) => return false,
                },
            }
        }

        // Process exited — decide whether to restart
        let should_restart = {
            let mut retries = self.retry_count.lock().unwrap();
            if *retries < MAX_RETRIES {
                *retries += 1;
                true
            } else {
                false
            }
        };

        if should_restart {
            *self.state.lock().unwrap() = SidecarState::Starting;
            let _ = self.start();
            true
        } else {
            *self.state.lock().unwrap() = SidecarState::Crashed;
            self.emit_state(SidecarStatePayload {
                state: "unhealthy",
                port: None,
                error: Some(
                    "Sidecar process crashed and exceeded maximum restart attempts".to_string(),
                ),
                timestamp: Self::unix_ts(),
            });
            false
        }
    }

    /// Gracefully shut down the sidecar.
    ///
    /// On Unix, sends SIGTERM via the system `kill` command and waits up to
    /// SHUTDOWN_WAIT_SECS seconds for the process to exit before force-killing.
    /// On Windows, immediately calls `kill()` (no SIGTERM equivalent).
    ///
    /// Emits `sidecar-state { state: "stopped" }` after the process exits.
    pub fn shutdown(&self) {
        let mut child_guard = self.child.lock().unwrap();
        if let Some(child) = child_guard.as_mut() {
            // Attempt graceful termination
            #[cfg(unix)]
            {
                let pid = child.id();
                let _ = Command::new("kill")
                    .arg("-TERM")
                    .arg(pid.to_string())
                    .status();
            }

            // On Windows there is no SIGTERM; fall straight to kill() after the wait.
            // Wait up to SHUTDOWN_WAIT_SECS for the process to exit gracefully.
            let deadline = Instant::now() + Duration::from_secs(SHUTDOWN_WAIT_SECS);
            loop {
                if Instant::now() > deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    break;
                }
                match child.try_wait() {
                    Ok(Some(_)) => break,
                    _ => std::thread::sleep(Duration::from_millis(100)),
                }
            }
        }
        *self.state.lock().unwrap() = SidecarState::Stopped;
        self.emit_state(SidecarStatePayload {
            state: "stopped",
            port: None,
            error: None,
            timestamp: Self::unix_ts(),
        });
    }

    pub fn state(&self) -> SidecarState {
        self.state.lock().unwrap().clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};

    // ── helpers ──────────────────────────────────────────────────────────────

    /// Bind an OS-assigned port, return the port number, and spawn a thread
    /// that accepts exactly one connection, reads the request, and responds with
    /// the supplied HTTP status line + body.
    fn spawn_mock_server(response: &'static str) -> u16 {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 1024];
                let _ = stream.read(&mut buf);
                let _ = stream.write_all(response.as_bytes());
            }
        });
        port
    }

    // ── existing tests (migrated to new_for_test) ────────────────────────────

    #[test]
    fn test_find_available_port() {
        let port = SidecarManager::find_available_port().unwrap();
        assert!(port > 1024, "Port should be > 1024, got {}", port);
        assert!(port < 65535, "Port should be < 65535, got {}", port);
    }

    #[test]
    fn test_health_url_format() {
        let mgr = SidecarManager::new_for_test(12345);
        assert_eq!(mgr.health_url(), "http://127.0.0.1:12345/api/v1/health");
    }

    #[test]
    fn test_initial_state_is_stopped() {
        let mgr = SidecarManager::new_for_test(12346);
        assert_eq!(mgr.state(), SidecarState::Stopped);
    }

    #[test]
    fn test_max_retries_constant() {
        assert_eq!(MAX_RETRIES, 3);
    }

    #[test]
    fn test_shutdown_wait_constant() {
        assert_eq!(SHUTDOWN_WAIT_SECS, 5);
    }

    #[test]
    fn test_health_poll_timeout_constant() {
        assert_eq!(HEALTH_POLL_TIMEOUT_SECS, 30);
    }

    #[test]
    fn test_port_is_set_on_new() {
        let port = SidecarManager::find_available_port().unwrap();
        assert!(port > 0);
    }

    #[test]
    fn test_check_health_returns_false_for_closed_port() {
        let mgr = SidecarManager::new_for_test(1); // port 1 is never open in userspace
        assert!(!mgr.check_health());
    }

    #[test]
    fn test_monitor_returns_false_when_no_child() {
        let mgr = SidecarManager::new_for_test(12347);
        assert!(!mgr.monitor());
    }

    #[test]
    fn test_state_transitions() {
        let mgr = SidecarManager::new_for_test(12348);
        assert_eq!(mgr.state(), SidecarState::Stopped);

        *mgr.state.lock().unwrap() = SidecarState::Starting;
        assert_eq!(mgr.state(), SidecarState::Starting);

        *mgr.state.lock().unwrap() = SidecarState::Ready;
        assert_eq!(mgr.state(), SidecarState::Ready);

        *mgr.state.lock().unwrap() = SidecarState::Crashed;
        assert_eq!(mgr.state(), SidecarState::Crashed);
    }

    #[test]
    fn test_shutdown_sets_state_to_stopped() {
        let mgr = SidecarManager::new_for_test(12349);
        *mgr.state.lock().unwrap() = SidecarState::Ready;
        // shutdown with no child should just update state; emit is a no-op without AppHandle
        mgr.shutdown();
        assert_eq!(mgr.state(), SidecarState::Stopped);
    }

    // ── new health-check tests ────────────────────────────────────────────────

    /// Positive path: `check_health()` returns `true` when the server responds
    /// with HTTP 200 and a valid health JSON body.
    #[test]
    fn test_health_check_returns_true_on_200() {
        let body = r#"{"status":"ok","version":"2.0.0","ollama":true,"uptime":1.5}"#;
        let response = format!(
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n{}",
            body.len(),
            body
        );
        // Leak the string so we get a &'static str for the mock server.
        let port = spawn_mock_server(Box::leak(response.into_boxed_str()));

        std::thread::sleep(Duration::from_millis(20));

        let mgr = SidecarManager::new_for_test(port);
        assert!(
            mgr.check_health(),
            "check_health() should return true when server responds with HTTP 200 and valid JSON"
        );
    }

    /// Positive path: `check_health()` returns `true` for a degraded (207) response.
    #[test]
    fn test_health_check_returns_true_on_207_degraded() {
        let body = r#"{"status": "degraded","version":"2.0.0","ollama":false,"uptime":3.0}"#;
        let response = format!(
            "HTTP/1.1 207 Multi-Status\r\nContent-Length: {}\r\n\r\n{}",
            body.len(),
            body
        );
        let port = spawn_mock_server(Box::leak(response.into_boxed_str()));

        std::thread::sleep(Duration::from_millis(20));

        let mgr = SidecarManager::new_for_test(port);
        assert!(
            mgr.check_health(),
            "check_health() should return true for degraded (207) responses"
        );
    }

    /// Negative path: HTTP 200 but body has no valid status field.
    #[test]
    fn test_health_check_returns_false_on_200_without_status() {
        let port = spawn_mock_server(
            "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok",
        );

        std::thread::sleep(Duration::from_millis(20));

        let mgr = SidecarManager::new_for_test(port);
        assert!(
            !mgr.check_health(),
            "check_health() should return false when body lacks valid status JSON"
        );
    }

    /// Negative path: `check_health()` returns `false` when nothing is
    /// listening on the target port (connection refused).
    #[test]
    fn test_health_check_returns_false_on_connection_refused() {
        // Bind a port to discover an available number, then drop the listener
        // immediately so the port is closed by the time check_health() runs.
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener); // port is now closed

        let mgr = SidecarManager::new_for_test(port);
        assert!(
            !mgr.check_health(),
            "check_health() should return false when connection is refused"
        );
    }

    /// Negative path: `check_health()` returns `false` when the server replies
    /// with a non-200 status (e.g. 503 Service Unavailable).
    #[test]
    fn test_health_check_returns_false_on_non_200() {
        let port = spawn_mock_server(
            "HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n",
        );

        std::thread::sleep(Duration::from_millis(20));

        let mgr = SidecarManager::new_for_test(port);
        assert!(
            !mgr.check_health(),
            "check_health() should return false for non-200 responses"
        );
    }

    /// `unix_ts()` must return a plausible Unix timestamp (after 2024-01-01).
    #[test]
    fn test_unix_ts_is_reasonable() {
        let ts = SidecarManager::unix_ts();
        // 2024-01-01T00:00:00Z in Unix time = 1_704_067_200
        assert!(ts > 1_704_067_200, "Timestamp looks too old: {}", ts);
    }
}
