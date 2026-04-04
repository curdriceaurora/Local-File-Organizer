"""Tests for Windows application manifest XML structure and content.

Validates that the Windows manifest file exists, is valid XML, and contains
all required entries for a properly configured Windows desktop application.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

MANIFEST_PATH = Path(__file__).parent.parent.parent / "desktop" / "build" / "app.manifest"

# XML namespace map used in the manifest
NS = {
    "asm1": "urn:schemas-microsoft-com:asm.v1",
    "asm3": "urn:schemas-microsoft-com:asm.v3",
    "compat": "urn:schemas-microsoft-com:compatibility.v1",
    "dpi2005": "http://schemas.microsoft.com/SMI/2005/WindowsSettings",
    "dpi2016": "http://schemas.microsoft.com/SMI/2016/WindowsSettings",
}

# Windows 10 supportedOS GUID
WINDOWS_10_GUID = "{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"


class TestWindowsManifestExists:
    """Verify the manifest file is present in the expected location."""

    def test_manifest_file_exists(self) -> None:
        """The app.manifest file must exist at desktop/build/app.manifest."""
        assert MANIFEST_PATH.exists(), (
            f"Windows manifest not found at {MANIFEST_PATH}. "
            "Run the Windows manifest creation step."
        )

    def test_manifest_is_not_empty(self) -> None:
        """The manifest file must not be empty."""
        assert MANIFEST_PATH.stat().st_size > 0, "app.manifest is empty."


class TestWindowsManifestXML:
    """Verify the manifest is valid, well-formed XML."""

    @pytest.fixture(scope="class")
    def manifest_tree(self) -> ET.ElementTree:
        """Parse the manifest XML once for the test class."""
        try:
            return ET.parse(str(MANIFEST_PATH))
        except ET.ParseError as exc:
            pytest.fail(f"app.manifest is not valid XML: {exc}")

    def test_xml_parses_without_error(self, manifest_tree: ET.ElementTree) -> None:
        """The manifest must be parseable XML with no syntax errors."""
        assert manifest_tree is not None

    def test_root_element_is_assembly(self, manifest_tree: ET.ElementTree) -> None:
        """Root element must be <assembly> with the correct namespace."""
        root = manifest_tree.getroot()
        expected_tag = "{urn:schemas-microsoft-com:asm.v1}assembly"
        assert root.tag == expected_tag, f"Expected root tag '{expected_tag}', got '{root.tag}'"

    def test_manifest_version_is_1_0(self, manifest_tree: ET.ElementTree) -> None:
        """The <assembly> element must declare manifestVersion='1.0'."""
        root = manifest_tree.getroot()
        assert root.get("manifestVersion") == "1.0", "assembly/@manifestVersion must be '1.0'"


class TestRequestedExecutionLevel:
    """Verify the privilege level is set to asInvoker (not Administrator)."""

    @pytest.fixture(scope="class")
    def manifest_root(self) -> ET.Element:
        """Return the parsed root element."""
        tree = ET.parse(str(MANIFEST_PATH))
        return tree.getroot()

    def test_requested_execution_level_exists(self, manifest_root: ET.Element) -> None:
        """A <requestedExecutionLevel> element must be present in the manifest."""
        # trustInfo > security > requestedPrivileges > requestedExecutionLevel
        trust_info = manifest_root.find(
            ".//asm3:trustInfo/asm3:security/asm3:requestedPrivileges/asm3:requestedExecutionLevel",
            NS,
        )
        assert trust_info is not None, (
            "Could not find <requestedExecutionLevel> under trustInfo/security/requestedPrivileges."
        )

    def test_requested_execution_level_is_as_invoker(self, manifest_root: ET.Element) -> None:
        """requestedExecutionLevel/@level must be 'asInvoker', not 'requireAdministrator'."""
        trust_info = manifest_root.find(
            ".//asm3:trustInfo/asm3:security/asm3:requestedPrivileges/asm3:requestedExecutionLevel",
            NS,
        )
        assert trust_info is not None, "requestedExecutionLevel element not found."
        level = trust_info.get("level")
        assert level == "asInvoker", (
            f"requestedExecutionLevel/@level must be 'asInvoker', got '{level}'. "
            "Never request administrator privileges in the manifest."
        )

    def test_ui_access_is_false(self, manifest_root: ET.Element) -> None:
        """requestedExecutionLevel/@uiAccess must be 'false'."""
        trust_info = manifest_root.find(
            ".//asm3:trustInfo/asm3:security/asm3:requestedPrivileges/asm3:requestedExecutionLevel",
            NS,
        )
        assert trust_info is not None, "requestedExecutionLevel element not found."
        ui_access = trust_info.get("uiAccess")
        assert ui_access == "false", (
            f"requestedExecutionLevel/@uiAccess must be 'false', got '{ui_access}'."
        )


class TestSupportedOS:
    """Verify that Windows 10+ is declared as a supported OS."""

    @pytest.fixture(scope="class")
    def manifest_root(self) -> ET.Element:
        """Return the parsed root element."""
        tree = ET.parse(str(MANIFEST_PATH))
        return tree.getroot()

    def test_compatibility_section_exists(self, manifest_root: ET.Element) -> None:
        """A <compatibility> section must exist in the manifest."""
        compat = manifest_root.find(".//compat:application", NS)
        assert compat is not None, "No <compatibility><application> section found in manifest."

    def test_windows_10_supported_os_id_present(self, manifest_root: ET.Element) -> None:
        """The Windows 10 supportedOS GUID must be declared."""
        supported_os_elements = manifest_root.findall(
            ".//compat:application/compat:supportedOS", NS
        )
        assert supported_os_elements, "No <supportedOS> elements found in compatibility section."

        found_guids = [el.get("Id") for el in supported_os_elements]
        assert WINDOWS_10_GUID in found_guids, (
            f"Windows 10 GUID '{WINDOWS_10_GUID}' not found in supportedOS entries. "
            f"Found: {found_guids}"
        )


class TestDpiAwareness:
    """Verify DPI awareness settings for high-DPI display support."""

    @pytest.fixture(scope="class")
    def manifest_root(self) -> ET.Element:
        """Return the parsed root element."""
        tree = ET.parse(str(MANIFEST_PATH))
        return tree.getroot()

    def test_dpi_aware_element_exists(self, manifest_root: ET.Element) -> None:
        """A <dpiAware> element must be present in windowsSettings."""
        dpi_aware = manifest_root.find(
            ".//asm3:application/asm3:windowsSettings/dpi2005:dpiAware", NS
        )
        assert dpi_aware is not None, "<dpiAware> element not found in windowsSettings."

    def test_dpi_aware_is_true(self, manifest_root: ET.Element) -> None:
        """dpiAware must be set to 'true'."""
        dpi_aware = manifest_root.find(
            ".//asm3:application/asm3:windowsSettings/dpi2005:dpiAware", NS
        )
        assert dpi_aware is not None, "<dpiAware> element not found."
        assert dpi_aware.text is not None and dpi_aware.text.strip() == "true", (
            f"<dpiAware> must be 'true', got '{dpi_aware.text}'."
        )

    def test_dpi_awareness_element_exists(self, manifest_root: ET.Element) -> None:
        """A <dpiAwareness> element must be present in windowsSettings."""
        dpi_awareness = manifest_root.find(
            ".//asm3:application/asm3:windowsSettings/dpi2016:dpiAwareness", NS
        )
        assert dpi_awareness is not None, "<dpiAwareness> element not found in windowsSettings."

    def test_dpi_awareness_is_per_monitor_v2(self, manifest_root: ET.Element) -> None:
        """dpiAwareness must be set to 'PerMonitorV2' for best multi-monitor support."""
        dpi_awareness = manifest_root.find(
            ".//asm3:application/asm3:windowsSettings/dpi2016:dpiAwareness", NS
        )
        assert dpi_awareness is not None, "<dpiAwareness> element not found."
        assert dpi_awareness.text is not None and dpi_awareness.text.strip() == "PerMonitorV2", (
            f"<dpiAwareness> must be 'PerMonitorV2', got '{dpi_awareness.text}'."
        )
