"""
Module to provide for a simplified way to scan for files.
"""

import argparse
import glob
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from py_walk import get_parser_from_list
from typing_extensions import Protocol

from application_file_scanner.git_processor import GitProcessor

LOGGER = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class ApplicationFileScannerOutputProtocol(Protocol):
    """
    Protocol to provide for redirection of output (standard or error).
    """

    def __call__(  # noqa: E704
        self,
        output_string: str,
    ) -> None: ...  # pragma: no cover


# pylint: enable=too-few-public-methods


@dataclass
class ApplicationFileScannerOptions:
    """Class to encapsulate the more finely grained options for the"""

    enable_directory_manual_exclusions: bool = True
    """Enables manual exclusions to be applied to the directories as early as possible.
    """
    enable_directory_gitignore_exclusions: bool = False
    """Enables external .gitignore checking applied to the directories as early as possible.
    """
    enable_path_gitignore_exclusions: bool = False
    """Enables external .gitignore checking applied to the final list of matching files.
    """


# pylint: disable=too-many-instance-attributes
@dataclass
class ApplicationFileScannerStatistics:
    """Class to contain statistics about a run of the scanner."""

    top_level_excluded_path_count: int = 0
    """Count of matches that were excluded manually at the top level.
    """
    top_level_gitignored_count: int = 0
    """Count of matches that were excluded via .gitignore at the top level.
    """
    globbed_path_count: int = 0
    """Count of the paths provided that required glob resolution.
    """
    unglobbed_path_count: int = 0
    """Count of non-globbed paths that were just normally processed.
    """
    directory_top_walk_count: int = 0
    """Count of times that the os.walk function was called.
    """
    directory_nested_walk_count: int = 0
    """Count of iterations through the results provided by the walk function.
    """
    directories_excluded_count: int = 0
    """Count of directories that were excluded manually.
    """
    directories_gitignored_count: int = 0
    """Count of directories that were excluded via .gitignore.
    """
    external_gitignore_check_count: int = 0
    """Count of times that Git was externally called to check paths.
    """
    external_gitignore_combined_times: float = 0.0
    """Total elapsed time that Git took to determine if the paths it was asked to check should be ignored.
    """


# pylint: enable=too-many-instance-attributes


class ApplicationFileScanner:
    """
    Class to provide for a simplified way to scan for files.
    """

    __scanner_statistics = ApplicationFileScannerStatistics()
    __max_gitignore_total_buffer_size_before_submit = 32000
    __gitignore_per_path_buffer_size = 25

    # pylint: disable=too-many-arguments
    @staticmethod
    def determine_files_to_scan_with_args(
        args: argparse.Namespace,
        default_extensions_to_look_for: str = "",
        handle_output: Optional[ApplicationFileScannerOutputProtocol] = None,
        handle_error: Optional[ApplicationFileScannerOutputProtocol] = None,
        exclude_paths: Optional[List[str]] = None,
        scanner_options: Optional[ApplicationFileScannerOptions] = None,
    ) -> Tuple[List[str], bool, bool]:
        """
        Determine the files to scan based on the arguments provided by the `add_default_command_line_arguments` function.

        :param args: The argparse.Namespace object containing parsed command-line arguments.
        :type args: argparse.Namespace
        :param default_extensions_to_look_for: Comma separated list of extension to look for, unless overridden by args.alternate_extensions.
        :param handle_output: Optional function to handle standard output. Defaults to stdout.
        :type handle_output: Optional[ApplicationFileScannerOutputProtocol]
        :param handle_error: Optional function to handle error output. Defaults to stderr.
        :type handle_error: Optional[ApplicationFileScannerOutputProtocol]
        :param exclude_paths:  Optional list of paths to exclude, overriding 'args.path_exclusions'.
        :type exclude_paths: Optional[List[str]]
        :param scanner_options:  Optional settings that affect how files are scanned.
        :type exclude_paths: Optional[ApplicationFileScannerOptions]
        :returns: Tuple containing:
            - List of matching file paths,
            - Boolean indicating if any errors occurred,
            - Boolean indicating if only a file listing was requested.
        :rtype: Tuple[List[str], bool, bool]
        """

        if default_extensions_to_look_for:
            ApplicationFileScanner.is_valid_comma_separated_extension_list(
                default_extensions_to_look_for
            )
        alternate_extensions = getattr(args, "alternate_extensions", None)
        if alternate_extensions is not None:
            ApplicationFileScanner.is_valid_comma_separated_extension_list(
                alternate_extensions
            )

        extension_to_use = alternate_extensions or default_extensions_to_look_for

        # The command line argument being set to a non-default overrides the scanner options.
        if scanner_options is None:
            scanner_options = ApplicationFileScannerOptions()
        if getattr(args, "respect_gitignore", False):
            scanner_options.enable_directory_gitignore_exclusions = True
            scanner_options.enable_path_gitignore_exclusions = True

        return ApplicationFileScanner.determine_files_to_scan(
            args.paths,
            (
                exclude_paths
                if exclude_paths is not None
                else getattr(args, "path_exclusions", [])
            ),
            getattr(args, "recurse_directories", False),
            extension_to_use,
            getattr(args, "list_files", False),
            handle_output,
            handle_error,
            scanner_options,
        )

    # pylint: enable=too-many-arguments

    @staticmethod
    def __determine_files_to_scan_defaults(
        handle_output: Optional[ApplicationFileScannerOutputProtocol],
        handle_error: Optional[ApplicationFileScannerOutputProtocol],
        scanner_options: Optional[ApplicationFileScannerOptions],
    ) -> Tuple[
        ApplicationFileScannerOutputProtocol,
        ApplicationFileScannerOutputProtocol,
        ApplicationFileScannerOptions,
    ]:

        if handle_output is None:
            handle_output = ApplicationFileScanner.__default_standard_output
        if handle_error is None:
            handle_error = ApplicationFileScanner.__default_standard_error
        assert handle_output is not None
        assert handle_error is not None

        scanner_options = scanner_options or ApplicationFileScannerOptions()
        return handle_output, handle_error, scanner_options

    # pylint: disable=too-many-arguments
    @staticmethod
    def determine_files_to_scan(
        include_paths: List[str],
        exclude_paths: List[str],
        recurse_directories: bool,
        eligible_extensions: str,
        only_list_files: bool,
        handle_output: Optional[ApplicationFileScannerOutputProtocol] = None,
        handle_error: Optional[ApplicationFileScannerOutputProtocol] = None,
        scanner_options: Optional[ApplicationFileScannerOptions] = None,
    ) -> Tuple[List[str], bool, bool]:
        """
        Determine the files to scan, and how to scan for those files, using a direct interface.

        :param include_paths: List of path specifications (supports glob patterns) to include in the scan.
        :type include_paths: List[str]
        :param exclude_paths: List of path specifications (supports glob patterns) to exclude from the scan.
        :type exclude_paths: List[str]
        :param recurse_directories: If True, recursively scan directories.
        :type recurse_directories: bool
        :param eligible_extensions: Comma-separated string of file extensions (e.g. '.ext1,.ext2') to match.
        :type eligible_extensions: str
        :param only_list_files: If True, only list matching files without further processing.
        :type only_list_files: bool
        :param handle_output: Optional function to handle standard output. Defaults to stdout.
        :type handle_output: Optional[ApplicationFileScannerOutputProtocol]
        :param handle_error: Optional function to handle error output. Defaults to stderr.
        :type handle_error: Optional[ApplicationFileScannerOutputProtocol]
        :returns: Tuple containing:
            - List of matching file paths,
            - Boolean indicating if any errors occurred,
            - Boolean indicating if only a file listing was requested.
        :rtype: Tuple[List[str], bool, bool]
        """
        ApplicationFileScanner.__scanner_statistics = ApplicationFileScannerStatistics()

        split_eligible_extensions: List[str] = []
        if eligible_extensions:
            try:
                ApplicationFileScanner.is_valid_comma_separated_extension_list(
                    eligible_extensions
                )
                split_eligible_extensions = eligible_extensions.split(",")
            except argparse.ArgumentTypeError as this_exception:
                LOGGER.warning(
                    "One or more extensions to scan for are not valid: %s",
                    str(this_exception),
                )
                assert handle_error is not None
                handle_error(
                    f"One or more extensions to scan for are not valid: {this_exception}"
                )
                return [], True, False
        handle_output, handle_error, scanner_options = (
            ApplicationFileScanner.__determine_files_to_scan_defaults(
                handle_output, handle_error, scanner_options
            )
        )
        logging.debug(
            "determine_files_to_scan.include_paths        = %s", str(include_paths)
        )
        logging.debug(
            "determine_files_to_scan.exclude_paths        = %s", str(exclude_paths)
        )
        logging.debug(
            "determine_files_to_scan.eligible_extensions  = %s", eligible_extensions
        )
        logging.debug(
            "determine_files_to_scan.recurse_directories  = %s",
            str(recurse_directories),
        )
        logging.debug(
            "determine_files_to_scan.scanner_options      = %s", str(scanner_options)
        )

        did_error_scanning_files = False
        files_to_parse: Set[str] = set()
        for next_path in include_paths:
            did_error_scanning_files = (
                ApplicationFileScanner.__process_next_eligible_path(
                    next_path,
                    files_to_parse,
                    recurse_directories,
                    split_eligible_extensions,
                    handle_error,
                    scanner_options,
                    exclude_paths,
                )
            )
            if did_error_scanning_files:
                break

        sorted_files_to_parse, did_only_list_files = (
            ApplicationFileScanner.__determine_files_to_scan_epilog(
                files_to_parse,
                exclude_paths,
                scanner_options,
                only_list_files,
                handle_output,
                handle_error,
            )
        )
        return sorted_files_to_parse, did_error_scanning_files, did_only_list_files

    # pylint: enable=too-many-arguments

    # pylint: disable=too-many-arguments
    @staticmethod
    def __determine_files_to_scan_epilog(
        files_to_parse: Set[str],
        exclude_paths: List[str],
        scanner_options: ApplicationFileScannerOptions,
        only_list_files: bool,
        handle_output: ApplicationFileScannerOutputProtocol,
        handle_error: ApplicationFileScannerOutputProtocol,
    ) -> Tuple[List[str], bool]:
        if exclude_paths:
            pre_exclude_count = len(files_to_parse)
            files_to_parse = set(
                ApplicationFileScanner.__remove_any_manually_excluded_paths(
                    exclude_paths, list(files_to_parse)
                )
            )
            ApplicationFileScanner.__scanner_statistics.top_level_excluded_path_count += pre_exclude_count - len(
                files_to_parse
            )

        if files_to_parse and scanner_options.enable_path_gitignore_exclusions:
            files_to_parse = set(
                ApplicationFileScanner.__remove_any_gitignored_paths(files_to_parse)
            )

        sorted_files_to_parse = sorted(files_to_parse)
        LOGGER.info("Number of files found: %d", len(sorted_files_to_parse))
        did_only_list_files = ApplicationFileScanner.__handle_main_list_files(
            only_list_files, sorted_files_to_parse, handle_output, handle_error
        )
        return sorted_files_to_parse, did_only_list_files

    # pylint: enable=too-many-arguments

    @staticmethod
    def __glob_including_hidden(
        glob_pattern: str, recursive: bool = False
    ) -> List[str]:
        """
        A backward-compatible glob implementation that does not rely on the 3.11 or
        later include_hidden flag.

        :param glob_pattern: Pattern to pass to `glob.glob`.
        :param recursive: Whether the `**` pattern should match directories recursively.
        :return: List of all matching file paths.
        """

        hidden_pattern = os.path.join(
            os.path.dirname(glob_pattern) or ".",
            f".{os.path.basename(glob_pattern)}",
        )
        matches = glob.glob(glob_pattern, recursive=recursive)
        matches.extend(glob.glob(hidden_pattern, recursive=recursive))

        return sorted({os.path.normpath(m) for m in matches})

    # pylint: disable=too-many-arguments
    @staticmethod
    def __process_next_eligible_path(
        next_path: str,
        files_to_parse: Set[str],
        recurse_directories: bool,
        split_eligible_extensions: List[str],
        handle_error: ApplicationFileScannerOutputProtocol,
        scanner_options: ApplicationFileScannerOptions,
        exclude_paths: List[str],
    ) -> bool:
        did_error_scanning_files = False
        if "*" in next_path or "?" in next_path:

            logging.debug("processing globbed path: %s", next_path)
            ApplicationFileScanner.__scanner_statistics.globbed_path_count += 1
            globbed_paths = ApplicationFileScanner.__glob_including_hidden(
                next_path, recursive=True
            )

            if scanner_options.enable_directory_manual_exclusions:
                globbed_paths = (
                    ApplicationFileScanner.__process_next_eligible_path_filters(
                        globbed_paths, exclude_paths
                    )
                )

            for next_globbed_path in globbed_paths:
                _, _ = ApplicationFileScanner.__process_next_path(
                    next_globbed_path,
                    files_to_parse,
                    recurse_directories,
                    split_eligible_extensions,
                    handle_error,
                    True,
                    scanner_options,
                    exclude_paths,
                )
        else:
            logging.debug("processing unglobbed path: %s", next_path)
            ApplicationFileScanner.__scanner_statistics.unglobbed_path_count += 1
            _, did_error_scanning_files = ApplicationFileScanner.__process_next_path(
                next_path,
                files_to_parse,
                recurse_directories,
                split_eligible_extensions,
                handle_error,
                False,
                scanner_options,
                exclude_paths,
            )
        return did_error_scanning_files

    # pylint: enable=too-many-arguments

    # pylint: disable=too-many-arguments
    @staticmethod
    def __process_next_path(
        next_path: str,
        files_to_parse: Set[str],
        recurse_directories: bool,
        eligible_extensions: List[str],
        handle_error: ApplicationFileScannerOutputProtocol,
        from_glob: bool,
        scanner_options: ApplicationFileScannerOptions,
        exclude_paths: List[str],
    ) -> Tuple[bool, bool]:
        did_find_any = False
        did_error_scanning_files = False
        LOGGER.info("Processing path '%s'.", next_path)
        if not os.path.exists(next_path):
            handle_error(f"Provided path '{next_path}' does not exist.")
            LOGGER.debug("Provided path '%s' does not exist.", next_path)
            did_error_scanning_files = True
        elif os.path.isdir(next_path):

            # There are two cases where we want to process the directory.  The first is
            # always if the recurse_directories flag was specified, as we want to go as
            # deep with that as possible.  The second is if the function was called with
            # the results from a glob, in which case, we want to processs at least one level
            # of the directory specified in the path.
            if recurse_directories or not from_glob:
                LOGGER.debug("Processing directory: %s", next_path)
                next_path = os.path.abspath(next_path)
                ApplicationFileScanner.__process_next_path_directory(
                    next_path,
                    files_to_parse,
                    recurse_directories,
                    eligible_extensions,
                    scanner_options,
                    exclude_paths,
                )
                did_find_any = True
            else:
                LOGGER.debug(
                    "Directory '%s' is either from a glob (%s) or was not told to recurse (%s). Skipping.",
                    next_path,
                    from_glob,
                    recurse_directories,
                )
        elif ApplicationFileScanner.__is_file_eligible_to_scan(
            next_path, eligible_extensions
        ):
            LOGGER.debug(
                "Provided path '%s' has a valid extension. Adding.",
                next_path,
            )
            normalized_path = (
                next_path.replace(os.altsep, os.sep) if os.altsep else next_path
            )
            files_to_parse.add(os.path.abspath(normalized_path))
            did_find_any = True
        else:
            LOGGER.debug(
                "Provided path '%s' does not have a valid extension (%s). Skipping.",
                next_path,
                str(eligible_extensions),
            )
        return did_find_any, did_error_scanning_files

    # pylint: enable=too-many-arguments

    @staticmethod
    def __process_next_path_directory_files(
        files: List[str],
        normalized_root: str,
        eligible_extensions: List[str],
        files_to_parse: Set[str],
    ) -> None:
        for file in files:
            rooted_file_path = f"{normalized_root}{file}"
            if ApplicationFileScanner.__is_file_eligible_to_scan(
                rooted_file_path, eligible_extensions
            ):
                files_to_parse.add(rooted_file_path)
                logging.debug(
                    "File '%s' has a valid extension. Adding.", rooted_file_path
                )
            else:
                logging.debug(
                    "File '%s' does not have a valid extension. Skipping.",
                    rooted_file_path,
                )

    # pylint: disable=too-many-arguments
    @staticmethod
    def __process_next_path_directory(
        next_path: str,
        files_to_parse: Set[str],
        recurse_directories: bool,
        eligible_extensions: List[str],
        scanner_options: ApplicationFileScannerOptions,
        exclude_paths: List[str],
    ) -> None:
        normalized_next_path = (
            next_path.replace(os.altsep, os.sep) if os.altsep else next_path
        )
        LOGGER.debug(
            "Provided path '%s' is a directory. Walking directory (%s).",
            next_path,
            normalized_next_path,
        )
        ApplicationFileScanner.__scanner_statistics.directory_top_walk_count += 1
        for root, dirs, files in os.walk(normalized_next_path, topdown=True):

            ApplicationFileScanner.__scanner_statistics.directory_nested_walk_count += 1
            logging.debug(
                "root = %s, #dirs = %d, #files=%d", root, len(dirs), len(files)
            )
            logging.debug("dirs = %s", str(dirs))
            logging.debug("files = %s", str(files))
            normalized_root = root.replace(os.altsep, os.sep) if os.altsep else root
            break_after_this_item = (
                not recurse_directories and normalized_root == normalized_next_path
            )
            normalized_root = (
                normalized_root
                if normalized_root.endswith(os.sep)
                else normalized_root + os.sep
            )
            if (
                scanner_options.enable_directory_manual_exclusions
                or scanner_options.enable_directory_gitignore_exclusions
            ):
                ApplicationFileScanner.__process_next_path_directory_filter(
                    normalized_root, dirs, exclude_paths, scanner_options
                )

            ApplicationFileScanner.__process_next_path_directory_files(
                files, normalized_root, eligible_extensions, files_to_parse
            )

            if break_after_this_item:
                logging.debug(
                    "Directory '%s' is not the root directory AND recursion is not enabled. Breaking.",
                    normalized_root,
                )
                break
        logging.debug("Directory walk completed.")

    # pylint: enable=too-many-arguments

    @staticmethod
    def __process_next_path_directory_filter(
        normalized_root: str,
        dirs: List[str],
        exclude_paths: List[str],
        scanner_options: ApplicationFileScannerOptions,
    ) -> None:
        pre_exclude_count = len(dirs)
        ApplicationFileScanner.__filter_directory_walk_list(
            normalized_root, dirs, exclude_paths, scanner_options
        )
        post_exclude_count = len(dirs)
        if pre_exclude_count != post_exclude_count:
            logging.debug(
                "Active directories to process reduced from %d to %d.",
                pre_exclude_count,
                post_exclude_count,
            )
            logging.debug(
                "root (%s) dirs after filtering = %s",
                post_exclude_count,
                str(dirs),
            )
            ApplicationFileScanner.__scanner_statistics.directories_excluded_count += (
                pre_exclude_count - post_exclude_count
            )

    @staticmethod
    def __is_file_eligible_to_scan(
        path_to_test: str, eligible_extensions: List[str]
    ) -> bool:
        """
        Determine if the presented path is one that we want to scan.
        """
        return os.path.isfile(path_to_test) and (
            not eligible_extensions
            or any(
                path_to_test.endswith(next_extension)
                for next_extension in eligible_extensions
            )
        )

    # pylint: disable=too-many-arguments
    @staticmethod
    def add_default_command_line_arguments(
        parser_to_add_to: argparse.ArgumentParser,
        default_extensions_to_look_for: str,
        file_type_name: Optional[str] = None,
        show_list_files: bool = True,
        show_recurse_directories: bool = True,
        show_alternate_extensions: bool = True,
        show_exclusions: bool = True,
        show_respect_gitignore: bool = False,
    ) -> None:  # sourcery skip: use-assigned-variable
        """
        Add a set of default command line arguments to an argparse styled command line.

        :param parser_to_add_to: The ArgumentParser instance to add arguments to.
        :type parser_to_add_to: argparse.ArgumentParser
        :param default_extensions_to_look_for: Default file extension to scan for (e.g. '.txt').
        :type default_extensions_to_look_for: str
        :param file_type_name: Optional name of the file type for help text.
        :type file_type_name: Optional[str]
        :param show_list_files: If True, add argument to only list eligible files.
        :type show_list_files: bool
        :param show_recurse_directories: If True, add argument to enable recursive directory scanning.
        :type show_recurse_directories: bool
        :param show_alternate_extensions: If True, add argument to specify alternate file extensions.
        :type show_alternate_extensions: bool
        :param show_exclusions: If True, add argument to specify paths to exclude from scanning.
        :type show_exclusions: bool
        :param show_respect_gitignore: If True, respect any ignore paths set in the local .gitignore file.
        :type show_respect_gitignore: bool
        """

        default_alterate_extension: Optional[str] = default_extensions_to_look_for
        if default_extensions_to_look_for:
            ApplicationFileScanner.is_valid_comma_separated_extension_list(
                default_extensions_to_look_for
            )
        else:
            default_alterate_extension = None

        specific_file_type_name = ""
        if file_type_name is not None:
            if file_type_name := file_type_name.strip():
                specific_file_type_name = f"{file_type_name} "

        if show_list_files:
            parser_to_add_to.add_argument(
                "-l",
                "--list-files",
                dest="list_files",
                action="store_true",
                default=False,
                help=f"list any eligible {specific_file_type_name}files found on the specified paths and exit",
            )

        if show_recurse_directories:
            parser_to_add_to.add_argument(
                "-r",
                "--recurse",
                dest="recurse_directories",
                action="store_true",
                default=False,
                help="recursively traverse any found directories for matching files",
            )

        if show_alternate_extensions:
            parser_to_add_to.add_argument(
                "-ae",
                "--alternate-extensions",
                dest="alternate_extensions",
                action="store",
                default=default_alterate_extension,
                type=ApplicationFileScanner.is_valid_comma_separated_extension_list_and_disallow_empty_strings,
                help="provide an alternate set of file extensions to match against",
            )

        if show_exclusions:
            parser_to_add_to.add_argument(
                "-e",
                "--exclude",
                dest="path_exclusions",
                action="append",
                type=str,
                help="one or more paths to exclude from the search. Can be a glob pattern.",
            )

        if show_respect_gitignore:
            parser_to_add_to.add_argument(
                "--respect-gitignore",
                dest="respect_gitignore",
                action="store_true",
                default=False,
                help="respect any setting in the local .gitignore file.",
            )

        parser_to_add_to.add_argument(
            "paths",
            metavar="path",
            type=str,
            nargs="+",
            default=None,
            help=f"one or more paths to examine for eligible {specific_file_type_name}files",
        )

    # pylint: enable=too-many-arguments

    @staticmethod
    def __is_valid_extension(possible_extension: str) -> Optional[str]:
        """
        Determine if the parameter is a string that has the form of a valid extension.
        """
        if not possible_extension.startswith("."):
            return f"Extension '{possible_extension}' must start with a period."
        return (
            next(
                (
                    f"Extension '{possible_extension}' must only contain alphanumeric characters after the period."
                    for clean_split_char in clean_split
                    if not clean_split_char.isalnum()
                ),
                None,
            )
            if (clean_split := possible_extension[1:])
            else f"Extension '{possible_extension}' must have at least one character after the period."
        )

    @staticmethod
    def is_valid_comma_separated_extension_list_and_disallow_empty_strings(
        argument: str,
    ) -> str:
        """
        Validate a comma-separated list of file extensions for use with argparse.  Similar to
        is_valid_comma_separated_extension_list, but disallows an empty string.

        :param argument: Comma-separated string of file extensions to validate (e.g. '.txt,.log').
        :type argument: str
        :raises argparse.ArgumentTypeError: If any extension in the list is invalid.
        :returns: The validated, lowercased string of extensions.
        :rtype: str
        """
        if not argument:
            raise argparse.ArgumentTypeError(
                "Alternate extensions cannot be an empty string."
            )
        return ApplicationFileScanner.is_valid_comma_separated_extension_list(argument)

    @staticmethod
    def is_valid_comma_separated_extension_list(argument: str) -> str:
        """
        Validate a comma-separated list of file extensions for use with argparse.

        :param argument: Comma-separated string of file extensions to validate (e.g. '.txt,.log').
        :type argument: str
        :raises argparse.ArgumentTypeError: If any extension in the list is invalid.
        :returns: The validated, lowercased string of extensions.
        :rtype: str
        """
        if argument:
            split_argument = argument.split(",")
            for next_split in split_argument:
                if error_string := ApplicationFileScanner.__is_valid_extension(
                    next_split
                ):
                    raise argparse.ArgumentTypeError(error_string)
        return argument.lower()

    @staticmethod
    def __handle_main_list_files(
        only_list_files: bool,
        files_to_scan: List[str],
        handle_output: ApplicationFileScannerOutputProtocol,
        handle_error: ApplicationFileScannerOutputProtocol,
    ) -> bool:
        if only_list_files:
            LOGGER.info("Sending list of files that would have been scanned to stdout.")
            if files_to_scan:
                handle_output("\n".join(files_to_scan))
            else:
                handle_error("No matching files found.")
        return only_list_files

    @staticmethod
    def __default_standard_output(output_string: str) -> None:
        print(output_string)

    @staticmethod
    def __default_standard_error(output_string: str) -> None:
        print(output_string, file=sys.stderr)

    @staticmethod
    def __process_next_eligible_path_filters(
        globbed_paths: List[str], exclude_paths: List[str]
    ) -> List[str]:

        if not globbed_paths:
            return globbed_paths

        fully_pathed_and_normalized_globbed_paths: List[str] = [
            (
                os.path.abspath(i) + os.sep
                if os.path.isdir(os.path.abspath(i))
                else os.path.abspath(i)
            )
            for i in globbed_paths
        ]
        return ApplicationFileScanner.__remove_any_manually_excluded_paths(
            exclude_paths, fully_pathed_and_normalized_globbed_paths
        )

    @staticmethod
    def __filter_directory_walk_list(
        normalized_root: str,
        dirs: List[str],
        exclude_paths: List[str],
        scanner_options: ApplicationFileScannerOptions,
    ) -> None:

        if not dirs:
            return

        # Create a list of fully pathed directories, removing any manually excluded directories
        # if the option is enabled.  If the option is disabled, the finished list is simply
        # the first list.
        fully_pathed_and_normalized_directories = [
            os.path.join(normalized_root, i) + os.sep for i in dirs
        ]
        if scanner_options.enable_directory_manual_exclusions:
            full_path_directories_after_manual_exclude = (
                ApplicationFileScanner.__remove_any_manually_excluded_paths(
                    exclude_paths, fully_pathed_and_normalized_directories
                )
            )
        else:
            full_path_directories_after_manual_exclude = (
                fully_pathed_and_normalized_directories
            )

        # The `dirs` list assumes the `normalized_root` is already taken care of,
        # so shift it back from a full path to a partial rooted path.
        partial_path_directories_after_manual_exclude: List[str] = []
        for next_path in full_path_directories_after_manual_exclude:
            assert next_path.endswith(os.sep) and next_path.startswith(normalized_root)
            partial_path_directories_after_manual_exclude.append(
                next_path[len(normalized_root) : -1]
            )

        # Checking against Git for ignores.  Note that `get_check_ignores` returns a list of
        # the files to ignore.  We pass in a full path list to be certain it understands
        # what we are asking for.
        adjusted_exclude_directory_paths: List[str] = []
        if scanner_options.enable_directory_gitignore_exclusions:
            start = time.perf_counter()
            excluded_full_directory_paths = GitProcessor.get_check_ignores(
                full_path_directories_after_manual_exclude
            )
            elapsed = time.perf_counter() - start
            ApplicationFileScanner.__scanner_statistics.external_gitignore_check_count += (
                1
            )
            ApplicationFileScanner.__scanner_statistics.external_gitignore_combined_times += (
                elapsed
            )

            if excluded_full_directory_paths is not None:
                for next_path in excluded_full_directory_paths:
                    assert next_path.endswith(os.sep) and next_path.startswith(
                        normalized_root
                    )
                    adjusted_exclude_directory_paths.append(
                        next_path[len(normalized_root) : -1]
                    )
                ApplicationFileScanner.__scanner_statistics.directories_gitignored_count += len(
                    excluded_full_directory_paths
                )

        # Resolve the partial path dirs list, copying over only directories that are not
        # excluded.  This is done separately with a `clear` and `extend` on the `dirs` object
        # to avoid having to pass something back.
        local_directory_paths_minus_excluded_paths = [
            i
            for i in partial_path_directories_after_manual_exclude
            if i not in adjusted_exclude_directory_paths
        ]
        dirs.clear()
        dirs.extend(local_directory_paths_minus_excluded_paths)

    @staticmethod
    def __remove_any_manually_excluded_paths(
        exclude_paths: List[str], files_to_parse: List[str]
    ) -> List[str]:

        if not exclude_paths:
            return files_to_parse

        # Ensure that the exclude paths are posix compliant (mainly for Windows), and construct the gitignore string.
        modified_exclude_paths = (
            [i.replace(os.sep, os.altsep) for i in exclude_paths]
            if os.altsep is not None
            else exclude_paths[:]
        )

        # Create the matcher and use it to determine what files should remain in the new list.
        parser = get_parser_from_list(modified_exclude_paths, base_dir=os.getcwd())
        return [i for i in files_to_parse if not parser.match(i)]

    @staticmethod
    def __remove_any_gitignored_paths_batch(
        files_to_parse: Set[str], files_to_check: List[str]
    ) -> None:
        start = time.perf_counter()
        excluded_full_directory_paths = GitProcessor.get_check_ignores(files_to_check)
        elapsed = time.perf_counter() - start
        ApplicationFileScanner.__scanner_statistics.external_gitignore_check_count += 1
        ApplicationFileScanner.__scanner_statistics.external_gitignore_combined_times += (
            elapsed
        )

        if excluded_full_directory_paths is not None:
            for next_path in excluded_full_directory_paths:
                files_to_parse.remove(next_path)

    @staticmethod
    def __remove_any_gitignored_paths(files_to_parse: Set[str]) -> Set[str]:

        pre_ignore_size = len(files_to_parse)

        files_to_check: List[str] = []
        estimated_total_file_path_length = 0
        for next_file_path in list(files_to_parse):
            files_to_check.append(next_file_path)
            estimated_total_file_path_length += (
                ApplicationFileScanner.__gitignore_per_path_buffer_size
                + len(next_file_path)
            )
            if (
                estimated_total_file_path_length
                > ApplicationFileScanner.__max_gitignore_total_buffer_size_before_submit
            ):
                ApplicationFileScanner.__remove_any_gitignored_paths_batch(
                    files_to_parse, files_to_check
                )
                files_to_check.clear()
                estimated_total_file_path_length = 0
        if files_to_check:  # pragma: no cover
            ApplicationFileScanner.__remove_any_gitignored_paths_batch(
                files_to_parse, files_to_check
            )

        ApplicationFileScanner.__scanner_statistics.top_level_gitignored_count += (
            pre_ignore_size - len(files_to_parse)
        )
        return files_to_parse

    @staticmethod
    def get_last_scan_statistics() -> ApplicationFileScannerStatistics:
        """Get the statistics from the last run of the scanner."""
        return ApplicationFileScanner.__scanner_statistics
