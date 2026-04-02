"""
Module to provide support to Application File Scanner to interface with Git.
"""

import os
import platform
import re
import subprocess  # nosec B404
from typing import List, Optional, Tuple


class GitProcessor:
    """
    Class to provide a facade for dealing with Git.
    """

    # On Windows, os.path.altsep is defined, on max and linux, it is None.  This resolves that
    # for this module to simplify things.
    __normalized_alternate_separator = os.path.altsep or os.path.sep

    @staticmethod
    def __run_git_command(
        directory_to_use: str, *args: str
    ) -> Tuple[int, Optional[str], Optional[str]]:

        try:
            result = subprocess.run(  # nosec B603
                ["git"] + list(args),
                capture_output=True,
                text=True,
                check=True,
                cwd=directory_to_use,
            )
            return (
                result.returncode,
                result.stdout.strip() if result.stdout is not None else None,
                result.stderr.strip() if result.stderr is not None else None,
            )
        except subprocess.CalledProcessError as this_exception:
            return this_exception.returncode, None, this_exception.stderr.strip()

    @staticmethod
    def get_version() -> Optional[str]:
        """Get the git version by invoking Git.  Useful for determining if git is installed.
        Note that this only detects if git is installed, not if the current directory is
        within a valid git project.

        :return: Optional string containing the version number, if git is installed.
        :rspec: Optional[str]
        """
        (
            return_code,
            git_version,
            _,
        ) = GitProcessor.__run_git_command(".", "--version")
        return git_version if return_code == 0 else None

    @staticmethod
    def get_current_directory_project_base() -> Optional[str]:
        """Given the currenty directory, return the current Git project's base directory.

        :return: None if the current directory is not within a Git project, or a string
                 if it is within a Git project.
        :rspec: Optional[str]
        """
        (
            _,
            project_base_directory,
            _,
        ) = GitProcessor.__run_git_command(".", "rev-parse", "--show-toplevel")
        if project_base_directory:
            project_base_directory = project_base_directory.replace(
                GitProcessor.__normalized_alternate_separator, os.path.sep
            )
        return project_base_directory

    @staticmethod
    def __get_check_ignores_internal(
        modified_paths: List[str], single_check_mode: bool
    ) -> Optional[List[str]]:
        modified_paths.insert(0, "check-ignore")
        (
            status_code,
            standard_out,
            standard_error,
        ) = GitProcessor.__run_git_command(".", *modified_paths)
        if status_code not in [0, 1]:
            if single_check_mode and status_code == 128:
                return []
            raise AssertionError(f"Unexpected error: {status_code}, {standard_error}")

        files_to_ignore: List[str] = []
        if standard_out:
            files_to_ignore.extend(
                i.replace(GitProcessor.__normalized_alternate_separator, os.path.sep)
                for i in standard_out.splitlines(False)
            )
        return files_to_ignore

    # pylint: disable=too-many-locals
    @staticmethod
    def get_check_ignores(paths_to_check: List[str]) -> Optional[List[str]]:
        """
        Given a set of paths to check, check them against the current project's
        .gitignore file.  Note that this function handles files which MAY be
        outside of the current Git project for the caller.
        """

        base_path = GitProcessor.get_current_directory_project_base()
        if not base_path:
            return None

        xbase_path = base_path.replace(
            os.path.sep, (GitProcessor.__normalized_alternate_separator)
        ) + (GitProcessor.__normalized_alternate_separator)
        modified_paths = [
            i.replace(os.path.sep, GitProcessor.__normalized_alternate_separator)
            for i in paths_to_check
        ]
        drive_pattern = re.compile(r"^[A-Za-z]:(/)?")
        special_paths_to_check: List[str] = []
        normal_paths_to_check: List[str] = []
        for i in modified_paths:
            if GitProcessor.__get_check_ignores_is_special_path(
                i, drive_pattern, xbase_path
            ):
                special_paths_to_check.append(i)
            else:
                normal_paths_to_check.append(i)
        files_to_ignore = []
        if normal_paths_to_check:
            x = GitProcessor.__get_check_ignores_internal(normal_paths_to_check, False)
            assert x is not None
            files_to_ignore = x
        for i in special_paths_to_check:
            checked_item = GitProcessor.__get_check_ignores_internal([i], True)
            assert checked_item is not None
            files_to_ignore.extend(checked_item)
        return files_to_ignore

    # pylint: enable=too-many-locals

    @staticmethod
    def __get_check_ignores_is_special_path(
        i: str, drive_pattern: re.Pattern[str], xbase_path: str
    ) -> bool:
        starts_with_separator = i.startswith(os.altsep or os.sep)
        starts_with_parent_directory_then_separator = i.startswith(
            f"..{os.altsep or os.sep}"
        )
        includes_separator_parent_directory_separator = (
            f"{os.altsep or os.sep}..{os.altsep or os.sep}" in i
        )
        is_windows_path_start = platform.system().lower() == "windows" and bool(
            drive_pattern.match(i)
        )
        is_starts_with_base_path = i.lower().startswith(xbase_path.lower())
        return (
            starts_with_separator
            or starts_with_parent_directory_then_separator
            or includes_separator_parent_directory_separator
            or (is_windows_path_start and not is_starts_with_base_path)
        )
