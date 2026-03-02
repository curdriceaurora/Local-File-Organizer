//! Linux systemd daemon manager implementation.
//!
//! Uses systemd user units for per-user daemon management.
//! Unit files are placed in `$XDG_CONFIG_HOME/systemd/user/` (falls back to `~/.config/systemd/user/`).

use super::DaemonManager;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

/// Manages the file organizer daemon via systemd user units on Linux.
pub struct LinuxDaemonManager {
    /// The systemd unit name (without `.service` extension).
    pub service_name: String,
}

impl LinuxDaemonManager {
    /// Create a new `LinuxDaemonManager` with the given service name.
    pub fn new(service_name: &str) -> Self {
        LinuxDaemonManager {
            service_name: service_name.to_string(),
        }
    }

    /// Returns the path to the systemd user unit file.
    ///
    /// Respects `$XDG_CONFIG_HOME` if set, falling back to `~/.config`.
    pub fn unit_file_path(&self) -> std::io::Result<PathBuf> {
        let config_dir = if let Ok(xdg) = env::var("XDG_CONFIG_HOME") {
            PathBuf::from(xdg)
        } else {
            let home = dirs_next::home_dir().ok_or_else(|| {
                std::io::Error::new(
                    std::io::ErrorKind::NotFound,
                    "Cannot determine home directory",
                )
            })?;
            home.join(".config")
        };
        Ok(config_dir
            .join("systemd")
            .join("user")
            .join(format!("{}.service", self.service_name)))
    }

    /// Generates the systemd unit file content for the given binary path.
    pub fn generate_unit_file(&self, binary_path: &Path) -> String {
        format!(
            "[Unit]\n\
             Description=File Organizer Daemon\n\
             After=network.target\n\
             \n\
             [Service]\n\
             Type=simple\n\
             ExecStart=\"{}\"\n\
             Restart=on-failure\n\
             RestartSec=5\n\
             \n\
             [Install]\n\
             WantedBy=default.target\n",
            binary_path.display()
        )
    }

    /// Run a `systemctl --user` subcommand with the service name.
    fn systemctl(&self, args: &[&str]) -> std::io::Result<std::process::Output> {
        let mut cmd = Command::new("systemctl");
        cmd.arg("--user");
        for arg in args {
            cmd.arg(arg);
        }
        cmd.arg(&self.service_name);
        cmd.output()
    }

    /// Run a `systemctl --user` subcommand WITHOUT appending the service name.
    fn systemctl_bare(&self, args: &[&str]) -> std::io::Result<std::process::Output> {
        let mut cmd = Command::new("systemctl");
        cmd.arg("--user");
        for arg in args {
            cmd.arg(arg);
        }
        cmd.output()
    }
}

impl DaemonManager for LinuxDaemonManager {
    /// Write the unit file and reload the systemd user daemon.
    fn install(&self, binary_path: &Path) -> std::io::Result<()> {
        let unit_path = self.unit_file_path()?;

        // Ensure parent directory exists.
        if let Some(parent) = unit_path.parent() {
            fs::create_dir_all(parent)?;
        }

        let content = self.generate_unit_file(binary_path);
        fs::write(&unit_path, content)?;

        // Reload systemd user daemon so it picks up the new unit.
        // Best-effort — may fail in non-systemd environments (containers, WSL, etc.).
        let _ = self.systemctl_bare(&["daemon-reload"]);
        Ok(())
    }

    /// Stop and disable the service, remove the unit file, then daemon-reload.
    fn uninstall(&self) -> std::io::Result<()> {
        // Best-effort stop and disable; ignore errors if not running.
        let _ = self.stop();
        let _ = self.disable_autostart();

        let unit_path = self.unit_file_path()?;
        if unit_path.exists() {
            fs::remove_file(&unit_path)?;
        }

        // Best-effort daemon-reload after removing unit file.
        let _ = self.systemctl_bare(&["daemon-reload"]);
        Ok(())
    }

    /// Start the daemon via systemd.
    fn start(&self) -> std::io::Result<()> {
        let output = self.systemctl(&["start"])?;
        if output.status.success() {
            Ok(())
        } else {
            Err(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!(
                    "systemctl --user start {} failed: {}",
                    self.service_name,
                    String::from_utf8_lossy(&output.stderr)
                ),
            ))
        }
    }

    /// Stop the daemon via systemd.
    fn stop(&self) -> std::io::Result<()> {
        let output = self.systemctl(&["stop"])?;
        if output.status.success() {
            Ok(())
        } else {
            Err(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!(
                    "systemctl --user stop {} failed: {}",
                    self.service_name,
                    String::from_utf8_lossy(&output.stderr)
                ),
            ))
        }
    }

    /// Returns true if `systemctl --user is-active <service>` returns "active".
    fn is_running(&self) -> bool {
        match self.systemctl(&["is-active"]) {
            Ok(output) => {
                let stdout = String::from_utf8_lossy(&output.stdout);
                stdout.trim() == "active"
            }
            Err(_) => false,
        }
    }

    /// Enable the service to start automatically on user login.
    fn enable_autostart(&self) -> std::io::Result<()> {
        let output = self.systemctl(&["enable"])?;
        if output.status.success() {
            Ok(())
        } else {
            Err(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!(
                    "systemctl --user enable {} failed: {}",
                    self.service_name,
                    String::from_utf8_lossy(&output.stderr)
                ),
            ))
        }
    }

    /// Disable the service from starting automatically on user login.
    fn disable_autostart(&self) -> std::io::Result<()> {
        let output = self.systemctl(&["disable"])?;
        if output.status.success() {
            Ok(())
        } else {
            Err(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!(
                    "systemctl --user disable {} failed: {}",
                    self.service_name,
                    String::from_utf8_lossy(&output.stderr)
                ),
            ))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_unit_file_content() {
        let mgr = LinuxDaemonManager::new("file-organizer");
        let content = mgr.generate_unit_file(&PathBuf::from("/usr/bin/file-organizer"));
        assert!(content.contains("[Unit]"));
        assert!(content.contains("[Service]"));
        assert!(content.contains("[Install]"));
        assert!(content.contains("Restart=on-failure"));
    }

    #[test]
    fn test_unit_file_path() {
        let mgr = LinuxDaemonManager::new("file-organizer");
        let path = mgr.unit_file_path().expect("unit_file_path should succeed");
        assert!(path.to_string_lossy().contains(".config/systemd/user"));
        assert!(path.to_string_lossy().ends_with(".service"));
    }

    #[test]
    fn test_service_name() {
        let mgr = LinuxDaemonManager::new("my-service");
        assert_eq!(mgr.service_name, "my-service");
    }

    #[test]
    fn test_unit_file_contains_binary_path() {
        let mgr = LinuxDaemonManager::new("file-organizer");
        let binary = PathBuf::from("/opt/file-organizer/bin/file-organizer");
        let content = mgr.generate_unit_file(&binary);
        assert!(content.contains(r#"ExecStart="/opt/file-organizer/bin/file-organizer""#));
    }

    #[test]
    fn test_unit_file_path_ends_with_service_name() {
        let mgr = LinuxDaemonManager::new("my-custom-daemon");
        let path = mgr.unit_file_path().expect("unit_file_path should succeed");
        assert!(path
            .to_string_lossy()
            .ends_with("my-custom-daemon.service"));
    }

    #[test]
    fn test_unit_file_restart_sec() {
        let mgr = LinuxDaemonManager::new("file-organizer");
        let content = mgr.generate_unit_file(&PathBuf::from("/usr/bin/file-organizer"));
        assert!(content.contains("RestartSec=5"));
    }

    #[test]
    fn test_unit_file_after_network() {
        let mgr = LinuxDaemonManager::new("file-organizer");
        let content = mgr.generate_unit_file(&PathBuf::from("/usr/bin/file-organizer"));
        assert!(content.contains("After=network.target"));
    }

    #[test]
    fn test_unit_file_wanted_by_default() {
        let mgr = LinuxDaemonManager::new("file-organizer");
        let content = mgr.generate_unit_file(&PathBuf::from("/usr/bin/file-organizer"));
        assert!(content.contains("WantedBy=default.target"));
    }
}
