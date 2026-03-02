//! Windows Scheduled Task daemon manager.
//!
//! Manages the file-organizer background daemon using Windows Task Scheduler
//! (`schtasks.exe`), which is the standard mechanism for per-user background
//! services on Windows without requiring administrative privileges.
//!
//! Auto-start on login is handled via the Windows Registry key:
//! `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`

use std::io::{self, ErrorKind};
use std::path::Path;
use std::process::Command;

use super::DaemonManager;

/// Manages the file-organizer daemon as a Windows Scheduled Task.
///
/// The task is created under the current user's context using `schtasks.exe`
/// with a login trigger, so it does not require administrator privileges.
/// Auto-start behaviour is additionally wired through the registry Run key.
pub struct WindowsDaemonManager {
    /// The scheduled task name used to identify the task in Task Scheduler,
    /// e.g. `"FileOrganizerDaemon"`.
    pub task_name: String,
}

impl WindowsDaemonManager {
    /// Create a new manager with the given scheduled task name.
    pub fn new(task_name: impl Into<String>) -> Self {
        Self {
            task_name: task_name.into(),
        }
    }

    /// Returns the registry key path used for autostart entries.
    ///
    /// This is `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
    pub fn autostart_registry_key() -> &'static str {
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
    }

    /// Returns the registry value name used for the autostart entry.
    fn autostart_value_name() -> &'static str {
        "FileOrganizer"
    }

    /// Build the `schtasks /create` command string for the given binary path.
    ///
    /// The created task:
    /// - Runs at user login (`/sc onlogon`)
    /// - Runs as the current user (`/ru ""`  means current user)
    /// - Does not require a password (`/rp ""`)
    /// - Runs with normal priority and does not require elevation
    pub fn build_create_command(&self, binary_path: &Path) -> String {
        let binary_str = binary_path
            .to_str()
            .unwrap_or("file-organizer-daemon.exe");
        format!(
            "schtasks /create /tn \"{}\" /tr \"{}\" /sc onlogon /ru \"\" /f",
            self.task_name, binary_str
        )
    }

    /// Execute a `schtasks.exe` command with the provided arguments.
    fn schtasks(&self, args: &[&str]) -> io::Result<()> {
        let status = Command::new("schtasks").args(args).status()?;
        if status.success() {
            Ok(())
        } else {
            Err(io::Error::new(
                ErrorKind::Other,
                format!(
                    "schtasks {} exited with non-zero status: {}",
                    args.join(" "),
                    status
                ),
            ))
        }
    }

    /// Execute a `reg.exe` command with the provided arguments.
    fn reg(&self, args: &[&str]) -> io::Result<()> {
        let status = Command::new("reg").args(args).status()?;
        if status.success() {
            Ok(())
        } else {
            Err(io::Error::new(
                ErrorKind::Other,
                format!(
                    "reg {} exited with non-zero status: {}",
                    args.join(" "),
                    status
                ),
            ))
        }
    }
}

impl DaemonManager for WindowsDaemonManager {
    /// Install the daemon as a Windows Scheduled Task.
    ///
    /// Creates a task that triggers on user login and runs the provided binary.
    /// The `/f` flag overwrites any existing task with the same name.
    fn install(&self, binary_path: &Path) -> io::Result<()> {
        let binary_str = binary_path.to_str().ok_or_else(|| {
            io::Error::new(ErrorKind::InvalidInput, "Binary path is not valid UTF-8")
        })?;
        self.schtasks(&[
            "/create",
            "/tn",
            &self.task_name,
            "/tr",
            binary_str,
            "/sc",
            "onlogon",
            "/ru",
            "",
            "/f",
        ])
    }

    /// Uninstall the daemon by deleting the scheduled task.
    ///
    /// Stops the running task first (ignoring errors), then deletes it.
    fn uninstall(&self) -> io::Result<()> {
        // Attempt to stop first; ignore errors (task may not be running).
        let _ = self.stop();

        self.schtasks(&["/delete", "/tn", &self.task_name, "/f"])
    }

    /// Start the daemon by running the scheduled task immediately.
    fn start(&self) -> io::Result<()> {
        self.schtasks(&["/run", "/tn", &self.task_name])
    }

    /// Stop the daemon by ending the scheduled task's running instance.
    fn stop(&self) -> io::Result<()> {
        self.schtasks(&["/end", "/tn", &self.task_name])
    }

    /// Returns `true` if the scheduled task is currently in the "Running" state.
    ///
    /// Queries the task in CSV format and checks for the "Running" status string.
    fn is_running(&self) -> bool {
        Command::new("schtasks")
            .args(["/query", "/tn", &self.task_name, "/fo", "csv"])
            .output()
            .map(|output| {
                let stdout = String::from_utf8_lossy(&output.stdout);
                stdout.contains("Running")
            })
            .unwrap_or(false)
    }

    /// Enable auto-start on user login via the Windows Registry Run key.
    ///
    /// Adds `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\FileOrganizer`
    /// pointing to the scheduled task runner command.
    fn enable_autostart(&self) -> io::Result<()> {
        // Build the command that Windows will run on login via the registry.
        // We use schtasks /run so the task itself manages the process lifecycle.
        let run_value = format!("schtasks /run /tn \"{}\"", self.task_name);
        self.reg(&[
            "add",
            Self::autostart_registry_key(),
            "/v",
            Self::autostart_value_name(),
            "/t",
            "REG_SZ",
            "/d",
            &run_value,
            "/f",
        ])
    }

    /// Disable auto-start on user login by removing the Registry Run key value.
    fn disable_autostart(&self) -> io::Result<()> {
        // /f suppresses the confirmation prompt; ignore error if value is absent.
        let result = self.reg(&[
            "delete",
            Self::autostart_registry_key(),
            "/v",
            Self::autostart_value_name(),
            "/f",
        ]);
        // Treat "value not found" as a success (already disabled).
        match result {
            Ok(()) => Ok(()),
            Err(e) if e.kind() == ErrorKind::Other => {
                // reg.exe returns non-zero when the value doesn't exist;
                // that is acceptable here.
                Ok(())
            }
            Err(e) => Err(e),
        }
    }
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    fn make_manager() -> WindowsDaemonManager {
        WindowsDaemonManager::new("FileOrganizerDaemon")
    }

    /// Verify that the task name is stored correctly.
    #[test]
    fn test_task_name() {
        let mgr = WindowsDaemonManager::new("FileOrganizerDaemon");
        assert_eq!(mgr.task_name, "FileOrganizerDaemon");
    }

    /// Verify that a different task name is preserved verbatim.
    #[test]
    fn test_task_name_custom() {
        let mgr = WindowsDaemonManager::new("MyCustomTask");
        assert_eq!(mgr.task_name, "MyCustomTask");
    }

    /// Verify that `build_create_command` produces a valid schtasks command string.
    #[test]
    fn test_schtasks_create_command() {
        let mgr = make_manager();
        let binary =
            PathBuf::from(r"C:\Program Files\file-organizer\file-organizer-daemon.exe");
        let cmd = mgr.build_create_command(&binary);

        assert!(
            cmd.contains("schtasks"),
            "Command should invoke schtasks: {cmd}"
        );
        assert!(
            cmd.contains("/create"),
            "Command should use /create flag: {cmd}"
        );
        assert!(
            cmd.contains("FileOrganizerDaemon"),
            "Command should include task name: {cmd}"
        );
        assert!(
            cmd.contains(r"C:\Program Files\file-organizer\file-organizer-daemon.exe"),
            "Command should include binary path: {cmd}"
        );
        assert!(
            cmd.contains("onlogon"),
            "Command should trigger on logon: {cmd}"
        );
    }

    /// Verify the autostart registry key path is correct.
    #[test]
    fn test_registry_key_path() {
        let path = WindowsDaemonManager::autostart_registry_key();
        assert!(
            path.contains(r"Microsoft\Windows\CurrentVersion\Run"),
            "Registry key should point to Run key: {path}"
        );
        assert!(
            path.starts_with("HKCU"),
            "Registry key should be under HKCU: {path}"
        );
    }

    /// Verify the autostart registry value name is stable.
    #[test]
    fn test_registry_value_name() {
        let name = WindowsDaemonManager::autostart_value_name();
        assert_eq!(name, "FileOrganizer");
    }

    /// Verify that `build_create_command` handles a path with spaces correctly.
    #[test]
    fn test_schtasks_create_command_path_with_spaces() {
        let mgr = make_manager();
        let binary = PathBuf::from(r"C:\Program Files\My App\daemon.exe");
        let cmd = mgr.build_create_command(&binary);

        assert!(
            cmd.contains(r"C:\Program Files\My App\daemon.exe"),
            "Binary path with spaces should be present: {cmd}"
        );
    }

    /// Verify that the manager implements DaemonManager via trait object.
    #[test]
    fn test_implements_daemon_manager_trait() {
        let mgr = make_manager();
        // Cast to trait object to verify the implementation satisfies the trait.
        let _trait_obj: &dyn DaemonManager = &mgr;
    }
}
