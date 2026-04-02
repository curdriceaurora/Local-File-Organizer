"""
Module to provide for a manner to load an ApplicationProperties object from a JSON file.
"""

import json
import os
from typing import Any, Callable, Dict, Optional, Tuple

import pyjson5

from application_properties.application_properties import ApplicationProperties
from application_properties.application_properties_loader_helper import (
    ApplicationPropertiesLoaderHelper,
)


# pylint: disable=too-few-public-methods
class ApplicationPropertiesJsonLoader:
    """
    Class to provide for a manner to load an ApplicationProperties object from a JSON file.
    """

    # pylint: disable=too-many-arguments

    @staticmethod
    def load_and_set(
        properties_object: ApplicationProperties,
        configuration_file: str,
        handle_error_fn: Optional[Callable[[str, Optional[Exception]], None]] = None,
        clear_property_map: bool = True,
        check_for_file_presence: bool = True,
        load_as_json5_file: bool = False,
    ) -> Tuple[bool, bool]:
        """
        Load the specified file and set it into the given properties object.
        """
        if check_for_file_presence and (
            not os.path.exists(configuration_file)
            or not os.path.isfile(configuration_file)
        ):
            return False, False

        configuration_map: Dict[Any, Any] = {}
        handle_error_fn = (
            ApplicationPropertiesLoaderHelper.set_error_handler_if_not_set(
                handle_error_fn
            )
        )

        if load_as_json5_file:
            did_have_one_error, configuration_map = (
                ApplicationPropertiesJsonLoader.__load_as_json5(
                    configuration_file, handle_error_fn
                )
            )
        else:
            did_have_one_error, configuration_map = (
                ApplicationPropertiesJsonLoader.__load_as_json(
                    configuration_file, handle_error_fn
                )
            )

        did_apply_map = False
        if not did_have_one_error and configuration_map:
            try:
                properties_object.load_from_dict(
                    configuration_map,
                    clear_map=clear_property_map,
                    allow_periods_in_keys=True,
                )
                did_apply_map = True
            except ValueError as this_exception:
                formatted_error = (
                    f"Specified configuration file '{configuration_file}' "
                    + f"is not valid: {str(this_exception)}"
                )
                did_have_one_error = True
                handle_error_fn(formatted_error, this_exception)
        return did_apply_map and not did_have_one_error, did_have_one_error

    # pylint: enable=too-many-arguments

    @staticmethod
    def __load_as_json(
        configuration_file: str,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, Dict[str, Any]]:
        did_have_one_error = False
        configuration_map: Dict[Any, Any] = {}
        try:
            with open(configuration_file, encoding="utf-8") as infile:
                sample_line = infile.readline()
                cur_pos = infile.tell()
                infile.seek(0, os.SEEK_END)
                end_pos = infile.tell()
                if sample_line.strip() == "" and cur_pos == end_pos:
                    configuration_map = {}
                else:
                    infile.seek(0, os.SEEK_SET)
                    configuration_map = json.load(infile)
        except json.decoder.JSONDecodeError as this_exception:
            formatted_error = (
                f"Specified configuration file '{configuration_file}' "
                + f"is not a valid JSON file: {str(this_exception)}."
            )
            did_have_one_error = True
            handle_error_fn(formatted_error, this_exception)
        except OSError as this_exception:
            formatted_error = (
                f"Specified configuration file '{configuration_file}' "
                + f"was not loaded: {str(this_exception)}."
            )
            did_have_one_error = True
            handle_error_fn(formatted_error, this_exception)
        return did_have_one_error, configuration_map

    # pylint: disable=no-member
    @staticmethod
    def __load_as_json5(
        configuration_file: str,
        handle_error_fn: Callable[[str, Optional[Exception]], None],
    ) -> Tuple[bool, Dict[str, Any]]:
        did_have_one_error = False
        configuration_map: Dict[Any, Any] = {}

        try:
            with open(configuration_file, encoding="utf-8") as infile:
                configuration_map = pyjson5.load(infile)
        except pyjson5.Json5EOF:
            configuration_map = {}
        except pyjson5.Json5DecoderException as this_exception:
            formatted_error = (
                f"Specified configuration file '{configuration_file}' "
                + f"is not a valid JSON file: {str(this_exception)}."
            )
            did_have_one_error = True
            handle_error_fn(formatted_error, this_exception)
        except OSError as this_exception:
            formatted_error = (
                f"Specified configuration file '{configuration_file}' "
                + f"was not loaded: {str(this_exception)}."
            )
            did_have_one_error = True
            handle_error_fn(formatted_error, this_exception)
        return did_have_one_error, configuration_map

    # pylint: enable=no-member


# pylint: enable=too-few-public-methods
