"""
Module containing the MultisourceConfigurationLoader class and its supporting classes.
"""

import contextlib
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional, Tuple

import pyjson5
import tomli
import yaml

from application_properties import ApplicationProperties
from application_properties.application_properties_json_loader import (
    ApplicationPropertiesJsonLoader,
)
from application_properties.application_properties_loader_helper import (
    ApplicationPropertiesLoaderHelper,
)
from application_properties.application_properties_toml_loader import (
    ApplicationPropertiesTomlLoader,
)
from application_properties.application_properties_yaml_loader import (
    ApplicationPropertiesYamlLoader,
)

LOGGER = logging.getLogger(__name__)


class ConfigurationFileType(Enum):
    """Represents the supported configuration file types for application properties.

    Used to distinguish between JSON, YAML, and TOML file types.
    """

    NONE = 0
    JSON = 1
    YAML = 2
    YML = 3
    TOML = 4


@dataclass
class MultisourceConfigurationLoaderOptions:
    """
    Options to modify the behavior of one of more configuration sources
    during the MultisourceConfigurationLoader processing of registered sources.
    """

    load_json_files_as_json5: bool = False
    """
    Allow parsing of JSON files using the JSON5 parser. (Default = False)
    """
    section_header_if_toml: Optional[str] = None
    """Optional section header to use when loading TOML configuration files.
    """


# pylint: disable=too-few-public-methods
class BaseConfigurationSource(ABC):
    """
    Base configuration source.
    """

    _file_type_to_extension_map = {
        ConfigurationFileType.JSON: ".json",
        ConfigurationFileType.YAML: ".yaml",
        ConfigurationFileType.YML: ".yml",
        ConfigurationFileType.TOML: ".toml",
    }

    @abstractmethod
    def apply_configuration(
        self,
        options: MultisourceConfigurationLoaderOptions,
        application_properties: ApplicationProperties,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, bool]:
        """
        Apply the current configuration source's configuration to the specified `ApplicationProperties` object.

        Args:
            options: Options to change the behavior of one of more configuration sources.
            application_properties: Instance of `ApplicationProperties` to apply the configuration to.
            handle_error_fn: Function to call if there are any errors when applying the configuration.
        """

    def __load_as_json(
        self,
        file_name: str,
        options: MultisourceConfigurationLoaderOptions,
        application_properties: ApplicationProperties,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, bool]:
        LOGGER.debug(
            "Attempting to find/load '%s' as a JSON configuration file.",
            file_name,
        )
        (
            did_apply_map,
            did_have_one_error,
        ) = ApplicationPropertiesJsonLoader.load_and_set(
            application_properties,
            file_name,
            handle_error_fn=handle_error_fn,
            clear_property_map=False,
            check_for_file_presence=True,
            load_as_json5_file=options.load_json_files_as_json5,
        )
        return did_apply_map, did_have_one_error

    def __load_as_yaml(
        self,
        file_name: str,
        application_properties: ApplicationProperties,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, bool]:

        LOGGER.debug(
            "Attempting to find/load '%s' as a YAML configuration file.",
            file_name,
        )
        (
            did_apply_map,
            did_have_one_error,
        ) = ApplicationPropertiesYamlLoader.load_and_set(
            application_properties,
            file_name,
            handle_error_fn=handle_error_fn,
            clear_property_map=False,
            check_for_file_presence=True,
        )
        return did_apply_map, did_have_one_error

    def __load_as_toml(
        self,
        file_name: str,
        options: MultisourceConfigurationLoaderOptions,
        application_properties: ApplicationProperties,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, bool]:

        LOGGER.debug(
            "Attempting to find/load '%s' as a TOML configuration file.",
            file_name,
        )
        (
            did_apply_map,
            did_have_one_error,
        ) = ApplicationPropertiesTomlLoader.load_and_set(
            application_properties,
            file_name,
            section_header=options.section_header_if_toml,
            handle_error_fn=handle_error_fn,
            clear_property_map=False,
            check_for_file_presence=True,
        )
        return did_apply_map, did_have_one_error

    # pylint: disable=too-many-arguments
    def _load_config(
        self,
        config_file_type: ConfigurationFileType,
        file_name: str,
        options: MultisourceConfigurationLoaderOptions,
        application_properties: ApplicationProperties,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, bool]:

        if config_file_type == ConfigurationFileType.JSON:
            return self.__load_as_json(
                file_name, options, application_properties, handle_error_fn
            )
        if config_file_type in [
            ConfigurationFileType.YAML,
            ConfigurationFileType.YML,
        ]:
            return self.__load_as_yaml(
                file_name, application_properties, handle_error_fn
            )
        assert config_file_type == ConfigurationFileType.TOML
        return self.__load_as_toml(
            file_name, options, application_properties, handle_error_fn
        )
        # return False, False

    # pylint: enable=too-many-arguments


# pylint: enable=too-few-public-methods


# pylint: disable=too-few-public-methods
class LocalPyprojectTomlFile(BaseConfigurationSource):
    """
    Class to allow the multisource configuration loader to reference a
    "pyproject.toml" file that may or may not exist.
    """

    __pyproject_toml_file = "pyproject.toml"

    def __init__(self, section_header_name: str) -> None:
        """
        Create an instance of the LocalPyprojectTomlFile object.

        Args:
            section_header_name: Name of the section within the `pyproject.toml`
                file containing the applications configuration.
        """
        self.__section_header_name = section_header_name

    def apply_configuration(
        self,
        options: MultisourceConfigurationLoaderOptions,
        application_properties: ApplicationProperties,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, bool]:

        _ = options

        LOGGER.debug(
            "Looking for local '%s' file.", LocalPyprojectTomlFile.__pyproject_toml_file
        )
        project_configuration_file = os.path.abspath(
            LocalPyprojectTomlFile.__pyproject_toml_file
        )
        return ApplicationPropertiesTomlLoader.load_and_set(
            application_properties,
            project_configuration_file,
            self.__section_header_name,
            handle_error_fn,
            clear_property_map=False,
            check_for_file_presence=True,
        )


# pylint: enable=too-few-public-methods


# pylint: disable=too-few-public-methods
class LocalProjectConfigurationFile(BaseConfigurationSource):
    """
    Class to allow the multisource configuration loader to reference a
    project configuration file that may or may not exist.
    """

    def __init__(
        self,
        project_file_name: str,
        config_file_type: ConfigurationFileType,
        alternate_extension_types: Optional[List[ConfigurationFileType]] = None,
    ) -> None:
        """
        Create an instance of the LocalPyprojectTomlFile object.

        When the `apply_configuration` function is called, it will first
        try and load the specified `project_file_name` file using the
        file type specified by `config_file_type`.  If a file with that name
        does not exist, it will change the extension of the file specified
        in `project_file_name` to zero or more of the extensions provided
        in the `alternate_extension_types` argument.  Note that only if
        the file is not present with that exact name will it proceed with
        using other extensions.

        Args:
            project_file_name: Name of the project configuration file to load.
            config_file_type: Format of data within the configuration file.
            alternate_extension_types: Optional set of file types to use by
                looking for project files with the same basename but different
                extensions.
        Raises:
            ValueError: If the config_file_type parameter is `ConfigurationFileType.NONE`.
        """
        self.project_file_name = project_file_name
        self.config_file_type = config_file_type
        self.alternate_extension_types = alternate_extension_types

        if self.config_file_type == ConfigurationFileType.NONE:
            raise ValueError(
                "Project configuration file must have a non-NONE file type set."
            )

    def apply_configuration(
        self,
        options: MultisourceConfigurationLoaderOptions,
        application_properties: ApplicationProperties,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, bool]:

        LOGGER.debug("Looking for local configuration files.")

        base_file_name = self.project_file_name
        abs_file_name = os.path.abspath(self.project_file_name)

        expected_file_type = BaseConfigurationSource._file_type_to_extension_map[
            self.config_file_type
        ]
        if base_file_name.endswith(expected_file_type):
            base_file_name = base_file_name[: -len(expected_file_type)]

        did_apply_map, did_have_one_error = self._load_config(
            self.config_file_type,
            abs_file_name,
            options,
            application_properties,
            handle_error_fn,
        )

        while (
            self.alternate_extension_types
            and not did_apply_map
            and not did_have_one_error
        ):
            top_alternate_extension_type = self.alternate_extension_types.pop(0)
            new_file_name = (
                os.path.abspath(base_file_name)
                + BaseConfigurationSource._file_type_to_extension_map[
                    top_alternate_extension_type
                ]
            )
            did_apply_map, did_have_one_error = self._load_config(
                top_alternate_extension_type,
                new_file_name,
                options,
                application_properties,
                handle_error_fn,
            )

        if not did_apply_map:
            LOGGER.debug("No default configuration files were loaded.")
        return did_apply_map, did_have_one_error


# pylint: enable=too-few-public-methods


# pylint: disable=too-few-public-methods
class SpecifiedConfigurationFile(BaseConfigurationSource):
    """
    Class to allow the multisource configuration loader to reference a
    specific configuration file provided, typically by the user.
    """

    def __init__(
        self,
        specified_file_name: Optional[str],
        config_file_type: ConfigurationFileType,
    ) -> None:
        """
        Create an instance of the SpecifiedConfigurationFile object.

        During the invocation of the `apply_configuration` function for this class,
        if the `config_file_type` parameter is `ConfigurationFileType.NONE`, a first
        pass will check to see if the extension of the file matches any of the file
        extensions registered to the configuration file types, using that as the
        configuration file type if a match is made. If that check fails to determine
        a file type, the second pass will check the contents of the file by using the
        base loaders for each of the file types.

        Args:
            specified_file_name: Name of configuration file to try and load.  If the name
                                 of the configuration file is empty or None, no attempt
                                 is made to load the file.
            config_file_type: Type of the configuration file being loaded.
        """
        self.specified_file_name = specified_file_name
        self.config_file_type = config_file_type

    # pylint: disable=no-member
    def __determine_file_type(
        self, options: MultisourceConfigurationLoaderOptions
    ) -> ConfigurationFileType:

        file_type = self.config_file_type
        assert self.specified_file_name

        if file_type == ConfigurationFileType.NONE:
            for i in ConfigurationFileType:
                if (
                    i != ConfigurationFileType.NONE
                    and self.specified_file_name.endswith(
                        BaseConfigurationSource._file_type_to_extension_map[i]
                    )
                ):
                    file_type = i
                    break
        if file_type == ConfigurationFileType.NONE:
            LOGGER.debug(
                "Attempt to determine file type for specified configuration file '%s' by content.",
                self.specified_file_name,
            )
            with open(self.specified_file_name, encoding="utf-8") as infile:
                if options.load_json_files_as_json5:
                    with contextlib.suppress(pyjson5.Json5DecoderException):
                        pyjson5.load(infile)
                        file_type = ConfigurationFileType.JSON
                else:
                    with contextlib.suppress(json.decoder.JSONDecodeError):
                        json.load(infile)
                        file_type = ConfigurationFileType.JSON
        if file_type == ConfigurationFileType.NONE:
            with contextlib.suppress(yaml.MarkedYAMLError):
                with open(self.specified_file_name, "rb") as infile:
                    _ = yaml.safe_load(infile)
                file_type = ConfigurationFileType.YAML
        if file_type == ConfigurationFileType.NONE:
            with contextlib.suppress(tomli.TOMLDecodeError):
                with open(self.specified_file_name, "rb") as infile:
                    tomli.load(infile)
                file_type = ConfigurationFileType.TOML
        return file_type

    # pylint: enable=no-member

    def apply_configuration(
        self,
        options: MultisourceConfigurationLoaderOptions,
        application_properties: ApplicationProperties,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, bool]:

        if not self.specified_file_name:
            return False, False

        if not os.path.isfile(self.specified_file_name):
            handle_error_fn(
                f"Specified configuration file `{self.specified_file_name}` does not exist.",
                None,
            )
            return False, True

        file_type = self.__determine_file_type(options)
        if file_type == ConfigurationFileType.NONE:
            formatted_error = f"Specified configuration file '{self.specified_file_name}' was not parseable as a JSON, YAML, or TOML file."
            LOGGER.warning(formatted_error)
            handle_error_fn(formatted_error, None)
            return False, True

        did_apply_map, did_have_one_error = self._load_config(
            file_type,
            self.specified_file_name,
            options,
            application_properties,
            handle_error_fn,
        )
        return did_apply_map, did_have_one_error


# pylint: enable=too-few-public-methods


# pylint: disable=too-few-public-methods
class ManuallySetProperties(BaseConfigurationSource):
    """
    Class to allow the multisource configuration loader to reference a
    zero or more individual properties, typically provided by the user.
    """

    def __init__(self, manual_properties: Optional[List[str]]) -> None:
        """
        Create an instance of the ManuallySetProperties object.

        During the invocation of the `apply_configuration` function for this class,
        if any string is not correctly formatted, the `handle_error_fn` function
        will be invoked stating the specific string that is not correctly formatted.

        For more information on the format of the property strings,
        consult the [documentation page](https://github.com/jackdewinter/application_properties/blob/main/docs/examples.md).

        Args:
            manual_properties: Optional list of strings properly formatted
                to denote the property keys and the values to set to them.
        """
        self.manual_properties = manual_properties

    def apply_configuration(
        self,
        options: MultisourceConfigurationLoaderOptions,
        application_properties: ApplicationProperties,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, bool]:

        _ = options

        did_apply = did_error = False
        if self.manual_properties:
            last_next_item = ""
            try:
                for next_item in self.manual_properties:
                    last_next_item = next_item
                    LOGGER.debug(
                        "Attempting to set manual property '%s'.",
                        next_item,
                    )
                    application_properties.set_manual_property(next_item)
                did_apply = True
            except ValueError as this_exception:
                formatted_error = f"Manually set property '{last_next_item}' was not validly formed: {this_exception}"
                handle_error_fn(formatted_error, this_exception)
                did_error = True

        return did_apply, did_error


# pylint: enable=too-few-public-methods


class MultisourceConfigurationLoader:
    """
    Class that serves as a container for classes descended from `BaseConfigurationSource`
    that are used to build the layers for configuration.
    """

    def __init__(
        self, options: Optional[MultisourceConfigurationLoaderOptions] = None
    ) -> None:
        """
        Create an instance of the `MultisourceConfigurationLoader` class with which
        to build the layers of configuration to apply and the order in which to
        apply them.

        Args:
            options: Optional settings that affect the processing of the
                configuration sources.
        """
        self.__configuration_sources: List[BaseConfigurationSource] = []
        self.__options = (
            options if options is not None else MultisourceConfigurationLoaderOptions()
        )

    def add_local_pyproject_toml_file(
        self, section_header_name: str
    ) -> "MultisourceConfigurationLoader":
        """
        Request that the multisource configuration loader tries to reference
        a "pyproject.toml" file that may or may not exist in the current directory.

        Args:
            section_header: Section header to look for within the "pyproject.toml" file.

        Returns:
            Instance of `self` for chaining `add_*` functions and the `process` function
            in a fluid manner.
        """
        self.__configuration_sources.append(LocalPyprojectTomlFile(section_header_name))
        return self

    def add_local_project_configuration_file(
        self,
        default_file_name: str,
        config_file_type: ConfigurationFileType,
        alternate_extension_types: Optional[List[ConfigurationFileType]] = None,
    ) -> "MultisourceConfigurationLoader":
        """
        Request that the multisource configuration loader tries to reference
        a project based configuration file that may exist in the current directory.

        When the `process` function is called, it will first
        try and load the specified `project_file_name` file using the
        file type specified by `config_file_type`.  If a file with that name
        does not exist, it will change the extension of the file specified
        in `project_file_name` to zero or more of the extensions provided
        in the `alternate_extension_types` argument.  Note that only if
        the file is not present with that exact name will it proceed with
        using other extensions.

        Args:
            default_file_name: Name of the default file to try and load.
            alternate_extension_types
        Returns:
            Instance of `self` for chaining `add_*` functions and the `process` function
            in a fluid manner.
        Raises:
            ValueError: If the config_file_type parameter is `ConfigurationFileType.NONE`.
        """
        self.__configuration_sources.append(
            LocalProjectConfigurationFile(
                default_file_name, config_file_type, alternate_extension_types
            )
        )
        return self

    def add_specified_configuration_file(
        self,
        config_file_name: Optional[str],
        config_file_type: ConfigurationFileType = ConfigurationFileType.NONE,
    ) -> "MultisourceConfigurationLoader":
        """
        Request that the multisource configuration loader tries to reference
        a configuration file that has been explicitly specified by the calling
        application.

        Note:
            During the invocation of the `process` function, if the `config_file_type`
            parameter is `ConfigurationFileType.NONE`, a first
            pass will check to see if the extension of the file matches any of the file
            extensions registered to the configuration file types, using that as the
            configuration file type if a match is made. If that check fails to determine
            a file type, the second pass will check the contents of the file by using the
            base loaders for each of the file types.


        Args:
            config_file_name: Name of configuration file to try and load.  If the name
                              of the configuration file is empty or None, no attempt
                              is made to load the file.
            config_file_type: Type of configuration file to load.  For auto-detecting
                              the file type, see the notes above.
            section_header_if_toml: Optional section header to use when loading
                              TOML configuration files.

        Returns:
            Instance of `self` for chaining `add_*` functions and the `process` function
            in a fluid manner.
        """
        self.__configuration_sources.append(
            SpecifiedConfigurationFile(config_file_name, config_file_type)
        )
        return self

    def add_manually_set_properties(
        self, manual_properties_to_set: Optional[List[str]] = None
    ) -> "MultisourceConfigurationLoader":
        """
        Request that the multisource configuration loader tries to use an
        array of strings to manually set configuration items for the user.
        Note that these strings are most often supplied as arguments to the
        command line of the application.

        During the invocation of the `process` function,
        if any string is not correctly formatted, the `handle_error_fn` function
        will be invoked stating the specific string that is not correctly formatted.

        For more information on the format,
        check [the documentation](https://github.com/jackdewinter/application_properties/blob/main/docs/examples.md)
        here.

        Args:
            manual_properties_to_set: Name of the default file to try and load.
        Returns:
            Instance of `self` for chaining `add_*` functions and the `process` function
            in a fluid manner.
        """
        self.__configuration_sources.append(
            ManuallySetProperties(manual_properties_to_set)
        )
        return self

    def add_custom_source(
        self, source_to_add: BaseConfigurationSource
    ) -> "MultisourceConfigurationLoader":
        """
        Request that the multisource configuration loader uses a custom
        configuration source.

        Args:
            source_to_add: Instance of a class that inherits from the `BaseConfigurationSource`
                class.
        Returns:
            Instance of `self` for chaining `add_*` functions and the `process` function
            in a fluid manner.
        Raises:
            ValueError: If the value provided to `source_to_add` is not an instance
                of the `BaseConfigurationSource` class.
        """
        if not isinstance(source_to_add, BaseConfigurationSource):
            raise ValueError(
                f"Added source '{source_to_add}' is not a valid configuration source."
            )

        self.__configuration_sources.append(source_to_add)
        return self

    def process(
        self,
        application_properties: ApplicationProperties,
        handle_error_fn: Optional[Callable[[str, Optional[Exception]], None]] = None,
    ) -> bool:
        """
        Process any registered configuration sources, stopping at the first sign of
        error.

        Args:
            application_properties: Instance of `ApplicationProperties` to apply the configuration to.
            handle_error_fn: Function to call if there are any errors when applying the configuration.
        """
        guaranteed_handle_error_fn: Callable[[str, Optional[Exception]], None] = (
            ApplicationPropertiesLoaderHelper.set_error_handler_if_not_set(
                handle_error_fn
            )
        )

        for next_configuration_source in self.__configuration_sources:
            _, did_error = next_configuration_source.apply_configuration(
                self.__options, application_properties, guaranteed_handle_error_fn
            )
            if did_error:
                return True
        return False
