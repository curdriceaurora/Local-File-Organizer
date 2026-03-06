"""Tests for Debian packaging files.

Validates that all required Debian packaging files exist and contain
the correct content for building a valid .deb package.
"""

import stat
from pathlib import Path

import pytest

# Base paths
REPO_ROOT = Path(__file__).parent.parent.parent
DEB_DIR = REPO_ROOT / "packaging" / "deb"
DEBIAN_DIR = DEB_DIR / "debian"


class TestDebianControl:
    """Tests for packaging/deb/debian/control."""

    def test_control_file_exists(self) -> None:
        """control file must exist in debian directory."""
        assert (DEBIAN_DIR / "control").exists(), "debian/control file not found"

    def test_control_package_field(self) -> None:
        """control file must contain Package: file-organizer."""
        content = (DEBIAN_DIR / "control").read_text()
        assert "Package: file-organizer" in content, (
            "debian/control missing 'Package: file-organizer'"
        )

    def test_control_version_field(self) -> None:
        """control file must contain a Version field with build-time placeholder."""
        content = (DEBIAN_DIR / "control").read_text()
        assert "Version: REPLACE_VERSION" in content, (
            "debian/control missing 'Version: REPLACE_VERSION' placeholder "
            "(version is injected at build time, not hardcoded)"
        )

    def test_control_architecture_field(self) -> None:
        """control file must contain Architecture: amd64."""
        content = (DEBIAN_DIR / "control").read_text()
        assert "Architecture: amd64" in content, "debian/control missing 'Architecture: amd64'"

    def test_control_depends_python3(self) -> None:
        """control Depends must include python3 >= 3.9."""
        content = (DEBIAN_DIR / "control").read_text()
        assert "python3 (>= 3.9)" in content, "debian/control Depends missing 'python3 (>= 3.9)'"

    def test_control_depends_libwebkit(self) -> None:
        """control Depends must include libwebkit2gtk-4.1-0."""
        content = (DEBIAN_DIR / "control").read_text()
        assert "libwebkit2gtk-4.1-0" in content, (
            "debian/control Depends missing 'libwebkit2gtk-4.1-0'"
        )

    def test_control_depends_appindicator(self) -> None:
        """control Depends must include libayatana-appindicator3-1."""
        content = (DEBIAN_DIR / "control").read_text()
        assert "libayatana-appindicator3-1" in content, (
            "debian/control Depends missing 'libayatana-appindicator3-1'"
        )

    def test_control_description_field(self) -> None:
        """control file must contain a Description field."""
        content = (DEBIAN_DIR / "control").read_text()
        assert "Description:" in content, "debian/control missing 'Description:' field"

    def test_control_homepage_field(self) -> None:
        """control file must contain the project Homepage."""
        content = (DEBIAN_DIR / "control").read_text()
        assert "Homepage: https://github.com/curdriceaurora/Local-File-Organizer" in content, (
            "debian/control missing correct Homepage field"
        )

    def test_control_maintainer_field(self) -> None:
        """control file must contain a Maintainer field."""
        content = (DEBIAN_DIR / "control").read_text()
        assert "Maintainer: File Organizer Team" in content, (
            "debian/control missing 'Maintainer: File Organizer Team'"
        )


class TestDebianRules:
    """Tests for packaging/deb/debian/rules."""

    def test_rules_file_exists(self) -> None:
        """rules file must exist in debian directory."""
        assert (DEBIAN_DIR / "rules").exists(), "debian/rules file not found"

    def test_rules_file_is_executable(self) -> None:
        """rules file must have executable permission."""
        rules_path = DEBIAN_DIR / "rules"
        file_stat = rules_path.stat()
        is_executable = bool(file_stat.st_mode & stat.S_IXUSR)
        assert is_executable, "debian/rules is not executable (missing user execute bit)"

    def test_rules_has_make_shebang(self) -> None:
        """rules file must start with the debhelper make shebang."""
        content = (DEBIAN_DIR / "rules").read_text()
        assert content.startswith("#!/usr/bin/make -f"), (
            "debian/rules must start with '#!/usr/bin/make -f'"
        )

    def test_rules_has_dh_wildcard(self) -> None:
        """rules file must contain the debhelper wildcard target."""
        content = (DEBIAN_DIR / "rules").read_text()
        assert "dh $@" in content, "debian/rules missing 'dh $@' debhelper wildcard rule"

    def test_rules_has_build_override(self) -> None:
        """rules file must have override_dh_auto_build for pre-built binaries."""
        content = (DEBIAN_DIR / "rules").read_text()
        assert "override_dh_auto_build" in content, (
            "debian/rules missing 'override_dh_auto_build' target"
        )


class TestDesktopEntry:
    """Tests for packaging/deb/file-organizer.desktop."""

    def test_desktop_file_exists(self) -> None:
        """Desktop entry file must exist."""
        assert (DEB_DIR / "file-organizer.desktop").exists(), "file-organizer.desktop not found"

    def test_desktop_entry_section(self) -> None:
        """Desktop entry must have [Desktop Entry] section header."""
        content = (DEB_DIR / "file-organizer.desktop").read_text()
        assert "[Desktop Entry]" in content, (
            "file-organizer.desktop missing '[Desktop Entry]' section"
        )

    def test_desktop_name_field(self) -> None:
        """Desktop entry must have Name=File Organizer."""
        content = (DEB_DIR / "file-organizer.desktop").read_text()
        assert "Name=File Organizer" in content, (
            "file-organizer.desktop missing 'Name=File Organizer'"
        )

    def test_desktop_exec_field(self) -> None:
        """Desktop entry must have correct Exec path."""
        content = (DEB_DIR / "file-organizer.desktop").read_text()
        assert "Exec=/usr/bin/file-organizer" in content, (
            "file-organizer.desktop missing 'Exec=/usr/bin/file-organizer'"
        )

    def test_desktop_type_field(self) -> None:
        """Desktop entry must have Type=Application."""
        content = (DEB_DIR / "file-organizer.desktop").read_text()
        assert "Type=Application" in content, "file-organizer.desktop missing 'Type=Application'"

    def test_desktop_categories_utility(self) -> None:
        """Desktop entry Categories must include Utility."""
        content = (DEB_DIR / "file-organizer.desktop").read_text()
        # Find the Categories line and verify Utility is present
        for line in content.splitlines():
            if line.startswith("Categories="):
                assert "Utility" in line, (
                    f"Desktop entry Categories does not include 'Utility': {line}"
                )
                return
        pytest.fail("file-organizer.desktop missing 'Categories=' field")

    def test_desktop_categories_file_manager(self) -> None:
        """Desktop entry Categories must include FileManager."""
        content = (DEB_DIR / "file-organizer.desktop").read_text()
        for line in content.splitlines():
            if line.startswith("Categories="):
                assert "FileManager" in line, (
                    f"Desktop entry Categories does not include 'FileManager': {line}"
                )
                return
        pytest.fail("file-organizer.desktop missing 'Categories=' field")

    def test_desktop_icon_field(self) -> None:
        """Desktop entry must have Icon field."""
        content = (DEB_DIR / "file-organizer.desktop").read_text()
        assert "Icon=file-organizer" in content, (
            "file-organizer.desktop missing 'Icon=file-organizer'"
        )

    def test_desktop_comment_field(self) -> None:
        """Desktop entry must have a Comment field."""
        content = (DEB_DIR / "file-organizer.desktop").read_text()
        assert "Comment=AI-powered local file organizer" in content, (
            "file-organizer.desktop missing expected Comment field"
        )


class TestDebianChangelog:
    """Tests for packaging/deb/debian/changelog."""

    def test_changelog_exists(self) -> None:
        """changelog file must exist in debian directory."""
        assert (DEBIAN_DIR / "changelog").exists(), "debian/changelog file not found"

    def test_changelog_package_name(self) -> None:
        """changelog first line must start with package name."""
        content = (DEBIAN_DIR / "changelog").read_text()
        first_line = content.splitlines()[0]
        assert first_line.startswith("file-organizer ("), (
            f"debian/changelog first line must start with 'file-organizer (', got: {first_line!r}"
        )

    def test_changelog_version_format(self) -> None:
        """changelog must have correct version string."""
        content = (DEBIAN_DIR / "changelog").read_text()
        assert "file-organizer (2.0.0-1)" in content, (
            "debian/changelog missing 'file-organizer (2.0.0-1)'"
        )

    def test_changelog_distribution(self) -> None:
        """changelog must specify a distribution (unstable)."""
        content = (DEBIAN_DIR / "changelog").read_text()
        first_line = content.splitlines()[0]
        assert "unstable" in first_line, (
            f"debian/changelog first line must contain 'unstable', got: {first_line!r}"
        )

    def test_changelog_urgency(self) -> None:
        """changelog must specify urgency field."""
        content = (DEBIAN_DIR / "changelog").read_text()
        first_line = content.splitlines()[0]
        assert "urgency=" in first_line, (
            f"debian/changelog first line must contain 'urgency=', got: {first_line!r}"
        )


class TestDebianCopyright:
    """Tests for packaging/deb/debian/copyright."""

    def test_copyright_exists(self) -> None:
        """copyright file must exist in debian directory."""
        assert (DEBIAN_DIR / "copyright").exists(), "debian/copyright file not found"

    def test_copyright_format_url(self) -> None:
        """copyright must have DEP-5 Format URL."""
        content = (DEBIAN_DIR / "copyright").read_text()
        assert (
            "Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/" in content
        ), "debian/copyright missing DEP-5 Format URL"

    def test_copyright_license_mit(self) -> None:
        """copyright must specify MIT license."""
        content = (DEBIAN_DIR / "copyright").read_text()
        assert "License: MIT" in content, "debian/copyright missing 'License: MIT'"

    def test_copyright_upstream_name(self) -> None:
        """copyright must have Upstream-Name field."""
        content = (DEBIAN_DIR / "copyright").read_text()
        assert "Upstream-Name: file-organizer" in content, (
            "debian/copyright missing 'Upstream-Name: file-organizer'"
        )


class TestDebianInstall:
    """Tests for packaging/deb/debian/install."""

    def test_install_exists(self) -> None:
        """install file must exist in debian directory."""
        assert (DEBIAN_DIR / "install").exists(), "debian/install file not found"

    def test_install_binary_path(self) -> None:
        """install file must map binary to /usr/bin/."""
        content = (DEBIAN_DIR / "install").read_text()
        assert "file-organizer usr/bin/" in content, (
            "debian/install missing 'file-organizer usr/bin/' mapping"
        )

    def test_install_desktop_path(self) -> None:
        """install file must map desktop entry to /usr/share/applications/."""
        content = (DEBIAN_DIR / "install").read_text()
        assert "file-organizer.desktop usr/share/applications/" in content, (
            "debian/install missing 'file-organizer.desktop usr/share/applications/' mapping"
        )


class TestPackagingStructure:
    """Integration tests for the overall packaging structure."""

    def test_deb_directory_exists(self) -> None:
        """packaging/deb directory must exist."""
        assert DEB_DIR.exists(), "packaging/deb directory not found"

    def test_debian_subdirectory_exists(self) -> None:
        """packaging/deb/debian subdirectory must exist."""
        assert DEBIAN_DIR.exists(), "packaging/deb/debian directory not found"

    def test_all_required_debian_files_present(self) -> None:
        """All required debian files must be present."""
        required_files = ["control", "rules", "changelog", "copyright", "install"]
        missing = [f for f in required_files if not (DEBIAN_DIR / f).exists()]
        assert not missing, f"Missing required debian files: {missing}"

    def test_desktop_file_in_deb_directory(self) -> None:
        """Desktop entry must be in packaging/deb/ (not debian/)."""
        assert (DEB_DIR / "file-organizer.desktop").exists(), (
            "file-organizer.desktop must be in packaging/deb/"
        )
