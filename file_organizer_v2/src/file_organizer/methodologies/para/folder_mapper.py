"""
PARA Category Folder Mapper

Maps files to PARA folders based on categorization results from heuristics
and rules. Provides flexible mapping strategies and subfolder organization.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .categories import PARACategory
from .config import PARAConfig
from .detection.heuristics import HeuristicEngine, HeuristicResult
from .folder_generator import PARAFolderGenerator
from .rules.engine import EvaluationContext, RuleEngine, RuleMatchResult

logger = logging.getLogger(__name__)


@dataclass
class MappingResult:
    """Result of mapping a file to a PARA folder."""

    source_path: Path
    target_category: PARACategory
    target_folder: Path
    confidence: float
    reasoning: list[str]
    subfolder_path: str | None = None


@dataclass
class MappingStrategy:
    """Strategy for organizing files within PARA categories."""

    # Organize by date (YYYY/MM or YYYY-MM)
    use_date_folders: bool = False
    date_format: str = "%Y/%m"  # Year/Month subfolders

    # Organize by file type
    use_type_folders: bool = False
    type_mapping: dict[str, str] | None = None  # Extension -> subfolder

    # Organize by content keywords
    use_keyword_folders: bool = False
    keyword_mapping: dict[str, str] | None = None  # Keyword -> subfolder

    # Custom subfolder function
    custom_subfolder_fn: Callable[[Path, PARACategory], str | None] | None = None


class CategoryFolderMapper:
    """
    Maps files to appropriate PARA folders based on categorization.

    Integrates with HeuristicEngine and RuleEngine to determine the best
    PARA category for each file, then generates the target folder path
    using configurable mapping strategies.
    """

    def __init__(
        self,
        config: PARAConfig | None = None,
        heuristic_engine: HeuristicEngine | None = None,
        rule_engine: RuleEngine | None = None,
        folder_generator: PARAFolderGenerator | None = None,
        strategy: MappingStrategy | None = None,
    ):
        """
        Initialize the category folder mapper.

        Args:
            config: PARA configuration
            heuristic_engine: Engine for heuristic-based categorization
            rule_engine: Engine for rule-based categorization (optional)
            folder_generator: Generator for PARA folder paths
            strategy: Strategy for subfolder organization
        """
        self.config = config or PARAConfig()

        # Initialize heuristic engine if not provided
        if heuristic_engine is None:
            self.heuristic_engine = HeuristicEngine(
                enable_temporal=self.config.enable_temporal_heuristic,
                enable_content=self.config.enable_content_heuristic,
                enable_structural=self.config.enable_structural_heuristic,
                enable_ai=self.config.enable_ai_heuristic,
            )
        else:
            self.heuristic_engine = heuristic_engine

        self.rule_engine = rule_engine
        self.folder_generator = folder_generator or PARAFolderGenerator(self.config)
        self.strategy = strategy or MappingStrategy()

    def map_file(
        self, file_path: Path, root_path: Path, use_rules: bool = True
    ) -> MappingResult:
        """
        Map a file to its target PARA folder.

        Args:
            file_path: Path to the file to map
            root_path: Root path of PARA structure
            use_rules: Whether to use rule engine if available

        Returns:
            MappingResult with target folder and reasoning
        """
        # Get categorization from heuristics
        heuristic_result = self.heuristic_engine.evaluate(file_path)
        category = heuristic_result.recommended_category
        confidence = heuristic_result.overall_confidence
        reasoning = self._extract_reasoning(heuristic_result, category)

        # Override with rules if available and enabled
        if use_rules and self.rule_engine is not None:
            rule_result = self._evaluate_rules(file_path)
            if rule_result is not None:
                category = PARACategory(rule_result.category)
                confidence = max(confidence, rule_result.confidence or 0.0)
                reasoning.insert(0, f"Rule '{rule_result.rule.name}' matched")

        # Default to Resource if no clear category
        if category is None:
            category = PARACategory.RESOURCE
            reasoning.append("Defaulted to Resource (no clear category)")

        # Get base category folder
        category_folder = self.folder_generator.get_category_path(
            category, root_path
        )

        # Apply mapping strategy for subfolder
        subfolder_path = self._determine_subfolder(file_path, category)

        # Build final target folder
        if subfolder_path:
            target_folder = category_folder / subfolder_path
        else:
            target_folder = category_folder

        return MappingResult(
            source_path=file_path,
            target_category=category,
            target_folder=target_folder,
            confidence=confidence,
            reasoning=reasoning,
            subfolder_path=subfolder_path,
        )

    def map_batch(
        self, file_paths: list[Path], root_path: Path, use_rules: bool = True
    ) -> list[MappingResult]:
        """
        Map multiple files to PARA folders.

        Args:
            file_paths: List of file paths to map
            root_path: Root path of PARA structure
            use_rules: Whether to use rule engine

        Returns:
            List of MappingResult objects
        """
        results = []
        for file_path in file_paths:
            try:
                result = self.map_file(file_path, root_path, use_rules)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to map {file_path}: {e}")
                # Create error result
                error_result = MappingResult(
                    source_path=file_path,
                    target_category=PARACategory.RESOURCE,
                    target_folder=root_path / self.config.resource_dir,
                    confidence=0.0,
                    reasoning=[f"Error during mapping: {str(e)}"],
                )
                results.append(error_result)
        return results

    def _evaluate_rules(self, file_path: Path) -> RuleMatchResult | None:
        """
        Evaluate file using rule engine.

        Args:
            file_path: Path to evaluate

        Returns:
            RuleMatchResult or None if no rules match
        """
        if self.rule_engine is None:
            return None

        # Create evaluation context
        context = EvaluationContext(file_path=file_path)

        # Evaluate rules
        try:
            result = self.rule_engine.evaluate_file(context)
            return result
        except Exception as e:
            logger.warning(f"Rule evaluation failed for {file_path}: {e}")
            return None

    def _extract_reasoning(
        self, result: HeuristicResult, category: PARACategory | None
    ) -> list[str]:
        """
        Extract reasoning from heuristic result.

        Args:
            result: Heuristic evaluation result
            category: Recommended category

        Returns:
            List of reasoning strings
        """
        reasoning: list[str] = []

        if category is None:
            return reasoning

        # Extract signals from category scores
        if category in result.scores:
            category_score = result.scores[category]
            reasoning.extend(category_score.signals[:3])  # Top 3 signals

        return reasoning

    def _determine_subfolder(
        self, file_path: Path, category: PARACategory
    ) -> str | None:
        """
        Determine subfolder path based on mapping strategy.

        Args:
            file_path: File being mapped
            category: PARA category

        Returns:
            Subfolder path or None
        """
        # Custom function takes precedence
        if self.strategy.custom_subfolder_fn:
            try:
                return self.strategy.custom_subfolder_fn(file_path, category)
            except Exception as e:
                logger.warning(f"Custom subfolder function failed: {e}")

        subfolder_parts = []

        # Date-based organization
        if self.strategy.use_date_folders:
            date_str = self._get_date_folder(file_path)
            if date_str:
                subfolder_parts.append(date_str)

        # Type-based organization
        if self.strategy.use_type_folders and self.strategy.type_mapping:
            ext = file_path.suffix.lower()
            if ext in self.strategy.type_mapping:
                subfolder_parts.append(self.strategy.type_mapping[ext])

        # Keyword-based organization
        if self.strategy.use_keyword_folders and self.strategy.keyword_mapping:
            keyword_folder = self._match_keyword_folder(file_path)
            if keyword_folder:
                subfolder_parts.append(keyword_folder)

        # Join all parts
        if subfolder_parts:
            return "/".join(subfolder_parts)

        return None

    def _get_date_folder(self, file_path: Path) -> str | None:
        """
        Get date-based subfolder from file modification time.

        Args:
            file_path: File path

        Returns:
            Date folder string or None
        """
        try:
            from datetime import datetime

            mtime = file_path.stat().st_mtime
            date = datetime.fromtimestamp(mtime)
            return date.strftime(self.strategy.date_format)
        except Exception as e:
            logger.warning(f"Failed to get date folder for {file_path}: {e}")
            return None

    def _match_keyword_folder(self, file_path: Path) -> str | None:
        """
        Match file to keyword-based subfolder.

        Args:
            file_path: File path

        Returns:
            Matched folder name or None
        """
        if not self.strategy.keyword_mapping:
            return None

        file_name_lower = file_path.name.lower()

        # Check each keyword
        for keyword, folder_name in self.strategy.keyword_mapping.items():
            if keyword.lower() in file_name_lower:
                return folder_name

        return None

    def create_target_folders(
        self, results: list[MappingResult], dry_run: bool = False
    ) -> dict[Path, bool]:
        """
        Create target folders for mapped files.

        Args:
            results: List of mapping results
            dry_run: If True, don't actually create folders

        Returns:
            Dictionary mapping folder paths to success status
        """
        folder_status = {}
        unique_folders = {result.target_folder for result in results}

        for folder in unique_folders:
            if dry_run:
                logger.info(f"[DRY RUN] Would create: {folder}")
                folder_status[folder] = True
            else:
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                    folder_status[folder] = True
                    logger.info(f"Created folder: {folder}")
                except Exception as e:
                    logger.error(f"Failed to create {folder}: {e}")
                    folder_status[folder] = False

        return folder_status

    def generate_mapping_report(
        self, results: list[MappingResult]
    ) -> str:
        """
        Generate human-readable report of mapping results.

        Args:
            results: List of mapping results

        Returns:
            Formatted report string
        """
        lines = [
            "# PARA Folder Mapping Report",
            "",
            f"Total files: {len(results)}",
            "",
            "## Distribution by Category",
        ]

        # Count by category
        by_category: dict[PARACategory, int] = {}
        for result in results:
            by_category[result.target_category] = (
                by_category.get(result.target_category, 0) + 1
            )

        for category, count in sorted(by_category.items()):
            percentage = (count / len(results) * 100) if results else 0
            lines.append(f"- {category.value.title()}: {count} files ({percentage:.1f}%)")

        lines.extend(["", "## Sample Mappings", ""])

        # Show first 10 mappings as examples
        for i, result in enumerate(results[:10]):
            lines.append(
                f"{i+1}. {result.source_path.name} → {result.target_category.value}"
            )
            lines.append(f"   Target: {result.target_folder}")
            lines.append(f"   Confidence: {result.confidence:.0%}")
            if result.reasoning:
                lines.append(f"   Reason: {result.reasoning[0]}")
            lines.append("")

        if len(results) > 10:
            lines.append(f"... and {len(results) - 10} more files")

        return "\n".join(lines)
