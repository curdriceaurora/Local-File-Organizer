"""Tests for Flatpak packaging manifest and AppStream metadata.

Validates that the Flatpak manifest is valid YAML with correct structure,
required permissions, and that the AppStream metainfo XML is well-formed.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

FLATPAK_DIR = Path(__file__).parent.parent.parent / "packaging" / "flatpak"
MANIFEST_PATH = FLATPAK_DIR / "com.fileorganizer.app.yml"
METAINFO_PATH = FLATPAK_DIR / "file-organizer.metainfo.xml"

EXPECTED_APP_ID = "com.fileorganizer.app"
EXPECTED_COMMAND = "file-organizer"

# Required finish-args for the sandbox permissions
REQUIRED_FINISH_ARGS = {
    "--filesystem=home",
    "--share=network",
    "--share=ipc",
    "--device=dri",
    "--socket=wayland",
    "--socket=fallback-x11",
}


class TestFlatpakManifestExists:
    """Verify the Flatpak manifest file is present."""

    def test_manifest_file_exists(self) -> None:
        """The com.fileorganizer.app.yml manifest must exist in packaging/flatpak/."""
        assert MANIFEST_PATH.exists(), (
            f"Flatpak manifest not found at {MANIFEST_PATH}. "
            "Create packaging/flatpak/com.fileorganizer.app.yml."
        )

    def test_manifest_is_not_empty(self) -> None:
        """The manifest file must not be empty."""
        assert MANIFEST_PATH.stat().st_size > 0, "Flatpak manifest file is empty."


class TestFlatpakManifestYAML:
    """Verify the manifest is valid, parseable YAML."""

    @pytest.fixture(scope="class")
    def manifest(self) -> dict:
        """Parse and return the Flatpak manifest as a dictionary."""
        try:
            with MANIFEST_PATH.open() as fh:
                data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            pytest.fail(f"com.fileorganizer.app.yml is not valid YAML: {exc}")
        assert isinstance(data, dict), "Manifest root must be a YAML mapping."
        return data

    def test_yaml_is_valid_and_parseable(self, manifest: dict) -> None:
        """The manifest must parse as valid YAML without errors."""
        assert manifest is not None
        assert len(manifest) > 0

    def test_app_id_is_correct_reverse_dns(self, manifest: dict) -> None:
        """app-id must follow reverse-DNS convention: com.fileorganizer.app."""
        app_id = manifest.get("app-id")
        assert app_id is not None, "Manifest is missing the 'app-id' field."
        assert app_id == EXPECTED_APP_ID, (
            f"Expected app-id '{EXPECTED_APP_ID}', got '{app_id}'. "
            "app-id must follow reverse-DNS naming convention."
        )

    def test_runtime_is_set(self, manifest: dict) -> None:
        """The 'runtime' field must be present and non-empty."""
        runtime = manifest.get("runtime")
        assert runtime is not None, "Manifest is missing the 'runtime' field."
        assert isinstance(runtime, str) and runtime.strip(), "'runtime' must be a non-empty string."

    def test_runtime_version_is_set(self, manifest: dict) -> None:
        """The 'runtime-version' field must be present."""
        runtime_version = manifest.get("runtime-version")
        assert runtime_version is not None, "Manifest is missing the 'runtime-version' field."

    def test_sdk_is_set(self, manifest: dict) -> None:
        """The 'sdk' field must be present and non-empty."""
        sdk = manifest.get("sdk")
        assert sdk is not None, "Manifest is missing the 'sdk' field."
        assert isinstance(sdk, str) and sdk.strip(), "'sdk' must be a non-empty string."

    def test_command_is_set(self, manifest: dict) -> None:
        """The 'command' field must be set to 'file-organizer'."""
        command = manifest.get("command")
        assert command is not None, "Manifest is missing the 'command' field."
        assert command == EXPECTED_COMMAND, (
            f"Expected command '{EXPECTED_COMMAND}', got '{command}'."
        )

    def test_modules_section_is_present(self, manifest: dict) -> None:
        """The 'modules' section must be present and contain at least one module."""
        modules = manifest.get("modules")
        assert modules is not None, "Manifest is missing the 'modules' section."
        assert isinstance(modules, list) and len(modules) > 0, "'modules' must be a non-empty list."


class TestFlatpakFinishArgs:
    """Verify all required sandbox permissions are declared in finish-args."""

    @pytest.fixture(scope="class")
    def finish_args(self) -> list[str]:
        """Parse and return the finish-args list from the manifest."""
        with MANIFEST_PATH.open() as fh:
            data = yaml.safe_load(fh)
        args = data.get("finish-args", [])
        assert isinstance(args, list), "'finish-args' must be a list."
        return args

    def test_finish_args_section_is_present(self, finish_args: list[str]) -> None:
        """The finish-args section must be present and non-empty."""
        assert len(finish_args) > 0, (
            "The 'finish-args' section is missing or empty. Sandbox permissions must be declared."
        )

    def test_filesystem_home_permission_is_present(self, finish_args: list[str]) -> None:
        """--filesystem=home must be present to allow access to user's home directory."""
        assert "--filesystem=home" in finish_args, (
            "'--filesystem=home' is missing from finish-args. "
            "The app requires access to the user's home directory to organize files."
        )

    def test_share_network_permission_is_present(self, finish_args: list[str]) -> None:
        """--share=network must be present for Ollama model inference networking."""
        assert "--share=network" in finish_args, (
            "'--share=network' is missing from finish-args. "
            "The app requires network access for local Ollama model communication."
        )

    def test_device_dri_permission_is_present(self, finish_args: list[str]) -> None:
        """--device=dri must be present for GPU-accelerated model inference."""
        assert "--device=dri" in finish_args, (
            "'--device=dri' is missing from finish-args. "
            "GPU access (DRI) is required for accelerated AI model inference."
        )

    def test_socket_wayland_permission_is_present(self, finish_args: list[str]) -> None:
        """--socket=wayland must be present for Wayland display server support."""
        assert "--socket=wayland" in finish_args, (
            "'--socket=wayland' is missing from finish-args. "
            "Wayland socket is required for the desktop UI on modern Linux."
        )

    def test_socket_fallback_x11_permission_is_present(self, finish_args: list[str]) -> None:
        """--socket=fallback-x11 must be present for X11 compatibility fallback."""
        assert "--socket=fallback-x11" in finish_args, (
            "'--socket=fallback-x11' is missing from finish-args. "
            "X11 fallback socket is required for compatibility with X11 sessions."
        )

    def test_all_required_permissions_are_present(self, finish_args: list[str]) -> None:
        """All required sandbox permissions must be present in finish-args."""
        missing = REQUIRED_FINISH_ARGS - set(finish_args)
        assert not missing, (
            f"Missing required finish-args permissions: {sorted(missing)}. "
            "All listed permissions are required for correct app operation."
        )


class TestMetainfoExists:
    """Verify the AppStream metainfo file is present."""

    def test_metainfo_file_exists(self) -> None:
        """The file-organizer.metainfo.xml file must exist in packaging/flatpak/."""
        assert METAINFO_PATH.exists(), (
            f"AppStream metainfo not found at {METAINFO_PATH}. "
            "Create packaging/flatpak/file-organizer.metainfo.xml."
        )

    def test_metainfo_is_not_empty(self) -> None:
        """The metainfo file must not be empty."""
        assert METAINFO_PATH.stat().st_size > 0, "AppStream metainfo file is empty."


class TestMetainfoXML:
    """Verify the AppStream metainfo XML is valid and well-formed."""

    @pytest.fixture(scope="class")
    def metainfo_tree(self) -> ET.ElementTree:
        """Parse the metainfo XML once for the test class."""
        try:
            return ET.parse(str(METAINFO_PATH))
        except ET.ParseError as exc:
            pytest.fail(f"file-organizer.metainfo.xml is not valid XML: {exc}")

    @pytest.fixture(scope="class")
    def metainfo_root(self, metainfo_tree: ET.ElementTree) -> ET.Element:
        """Return the root element of the parsed metainfo XML."""
        return metainfo_tree.getroot()

    def test_metainfo_xml_is_valid(self, metainfo_tree: ET.ElementTree) -> None:
        """The metainfo file must be parseable XML with no syntax errors."""
        assert metainfo_tree is not None

    def test_root_element_is_component(self, metainfo_root: ET.Element) -> None:
        """Root element must be <component> as required by AppStream spec."""
        assert metainfo_root.tag == "component", (
            f"Expected root element 'component', got '{metainfo_root.tag}'. "
            "AppStream metainfo must have <component> as the root element."
        )

    def test_component_type_is_desktop_application(self, metainfo_root: ET.Element) -> None:
        """The component type attribute must be 'desktop-application'."""
        component_type = metainfo_root.get("type")
        assert component_type == "desktop-application", (
            f"Expected component type 'desktop-application', got '{component_type}'."
        )

    def test_app_id_element_is_correct(self, metainfo_root: ET.Element) -> None:
        """The <id> element must match the Flatpak app-id: com.fileorganizer.app."""
        id_element = metainfo_root.find("id")
        assert id_element is not None, "<id> element is missing from metainfo."
        assert id_element.text == EXPECTED_APP_ID, (
            f"Expected metainfo <id> '{EXPECTED_APP_ID}', got '{id_element.text}'."
        )

    def test_name_element_is_present(self, metainfo_root: ET.Element) -> None:
        """The <name> element must be present and non-empty."""
        name_element = metainfo_root.find("name")
        assert name_element is not None, "<name> element is missing from metainfo."
        assert name_element.text and name_element.text.strip(), (
            "<name> element must have non-empty text content."
        )

    def test_summary_element_is_present(self, metainfo_root: ET.Element) -> None:
        """The <summary> element must be present and non-empty."""
        summary_element = metainfo_root.find("summary")
        assert summary_element is not None, "<summary> element is missing from metainfo."
        assert summary_element.text and summary_element.text.strip(), (
            "<summary> element must have non-empty text content."
        )

    def test_description_element_is_present(self, metainfo_root: ET.Element) -> None:
        """The <description> element must be present with content."""
        description_element = metainfo_root.find("description")
        assert description_element is not None, "<description> element is missing from metainfo."

    def test_license_element_is_present(self, metainfo_root: ET.Element) -> None:
        """The <project_license> element must be present."""
        license_element = metainfo_root.find("project_license")
        assert license_element is not None, "<project_license> element is missing from metainfo."
        assert license_element.text and license_element.text.strip(), (
            "<project_license> element must specify a license (e.g., MIT or Apache-2.0)."
        )
