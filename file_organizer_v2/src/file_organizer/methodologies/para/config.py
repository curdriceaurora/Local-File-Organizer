"""
PARA Configuration

Configuration management for PARA methodology including:
- Category thresholds
- Heuristic weights
- Auto-categorization rules
- Custom patterns and keywords
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import copy
import logging
import yaml

from .categories import PARACategory

logger = logging.getLogger(__name__)


@dataclass
class HeuristicWeights:
    """Weights for different heuristics."""
    temporal: float = 0.25
    content: float = 0.35
    structural: float = 0.30
    ai: float = 0.10

    def __post_init__(self) -> None:
        """Validate that weights sum to ~1.0 and are in valid range."""
        # Validate individual weights are in [0, 1]
        weights = [self.temporal, self.content, self.structural, self.ai]
        for i, (name, weight) in enumerate(zip(
            ['temporal', 'content', 'structural', 'ai'], weights
        )):
            if not (0.0 <= weight <= 1.0):
                raise ValueError(
                    f"{name} weight must be in [0.0, 1.0], got {weight}"
                )

        # Validate weights sum to ~1.0 (allow small floating point error)
        total = sum(weights)
        if not (0.99 <= total <= 1.01):
            raise ValueError(
                f"Heuristic weights must sum to 1.0, got {total:.4f}. "
                f"Current: temporal={self.temporal}, content={self.content}, "
                f"structural={self.structural}, ai={self.ai}"
            )


@dataclass
class CategoryThresholds:
    """Auto-categorization thresholds for each category."""
    project: float = 0.75
    area: float = 0.75
    resource: float = 0.80
    archive: float = 0.90

    def __post_init__(self) -> None:
        """Validate that all thresholds are in [0.0, 1.0]."""
        thresholds = {
            'project': self.project,
            'area': self.area,
            'resource': self.resource,
            'archive': self.archive
        }
        for name, threshold in thresholds.items():
            if not (0.0 <= threshold <= 1.0):
                raise ValueError(
                    f"{name} threshold must be in [0.0, 1.0], got {threshold}"
                )


@dataclass
class KeywordPatterns:
    """Custom keyword patterns for each category."""
    project: List[str] = field(default_factory=lambda: [
        "project", "deadline", "due", "sprint", "milestone",
        "deliverable", "proposal", "presentation"
    ])
    area: List[str] = field(default_factory=lambda: [
        "area", "ongoing", "recurring", "weekly", "monthly",
        "routine", "maintenance"
    ])
    resource: List[str] = field(default_factory=lambda: [
        "reference", "template", "guide", "tutorial",
        "documentation", "handbook", "manual"
    ])
    archive: List[str] = field(default_factory=lambda: [
        "archive", "old", "backup", "deprecated",
        "obsolete", "legacy", "completed"
    ])


@dataclass
class TemporalThresholds:
    """Time-based thresholds for categorization (in days)."""
    project_max_age: int = 30  # Files modified within last 30 days
    area_min_age: int = 30  # Areas are 30-180 days old
    area_max_age: int = 180
    resource_min_age: int = 60  # Resources are stable (60+ days)
    archive_min_age: int = 180  # Archives are 180+ days old
    archive_min_inactive: int = 90  # Not accessed for 90+ days


@dataclass
class PARAConfig:
    """Complete PARA configuration."""
    # Heuristic configuration
    heuristic_weights: HeuristicWeights = field(default_factory=HeuristicWeights)
    category_thresholds: CategoryThresholds = field(default_factory=CategoryThresholds)
    keyword_patterns: KeywordPatterns = field(default_factory=KeywordPatterns)
    temporal_thresholds: TemporalThresholds = field(default_factory=TemporalThresholds)

    # Feature flags
    enable_temporal_heuristic: bool = True
    enable_content_heuristic: bool = True
    enable_structural_heuristic: bool = True
    enable_ai_heuristic: bool = False

    # Behavior settings
    manual_review_threshold: float = 0.60  # Confidence below this requires manual review
    auto_categorize: bool = True  # Automatically categorize if confidence is high
    preserve_user_overrides: bool = True  # Remember user corrections

    # Directory settings
    default_root: Optional[Path] = None
    project_dir: str = "Projects"
    area_dir: str = "Areas"
    resource_dir: str = "Resources"
    archive_dir: str = "Archive"

    @classmethod
    def load_from_yaml(cls, config_path: Path) -> "PARAConfig":
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to YAML configuration file

        Returns:
            PARAConfig instance
        """
        if not config_path.exists():
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return cls()

        try:
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning("Empty config file, using defaults")
                return cls()

            # Parse heuristic weights
            heuristic_weights = HeuristicWeights(
                **data.get('heuristic_weights', {})
            )

            # Parse category thresholds
            category_thresholds = CategoryThresholds(
                **data.get('category_thresholds', {})
            )

            # Parse keyword patterns
            keyword_patterns = KeywordPatterns(
                **data.get('keyword_patterns', {})
            )

            # Parse temporal thresholds
            temporal_thresholds = TemporalThresholds(
                **data.get('temporal_thresholds', {})
            )

            # Parse default_root path with validation
            default_root = None
            if 'default_root' in data:
                try:
                    default_root = Path(data['default_root'])
                    # Validate that path string is reasonable (not empty, not just whitespace)
                    if not str(data['default_root']).strip():
                        logger.warning("default_root is empty, ignoring")
                        default_root = None
                except (TypeError, ValueError) as e:
                    logger.warning(f"Invalid default_root path '{data.get('default_root')}': {e}")
                    default_root = None

            # Create config
            config = cls(
                heuristic_weights=heuristic_weights,
                category_thresholds=category_thresholds,
                keyword_patterns=keyword_patterns,
                temporal_thresholds=temporal_thresholds,
                enable_temporal_heuristic=data.get('enable_temporal_heuristic', True),
                enable_content_heuristic=data.get('enable_content_heuristic', True),
                enable_structural_heuristic=data.get('enable_structural_heuristic', True),
                enable_ai_heuristic=data.get('enable_ai_heuristic', False),
                manual_review_threshold=data.get('manual_review_threshold', 0.60),
                auto_categorize=data.get('auto_categorize', True),
                preserve_user_overrides=data.get('preserve_user_overrides', True),
                default_root=default_root,
                project_dir=data.get('project_dir', 'Projects'),
                area_dir=data.get('area_dir', 'Areas'),
                resource_dir=data.get('resource_dir', 'Resources'),
                archive_dir=data.get('archive_dir', 'Archive'),
            )

            logger.info(f"Loaded configuration from {config_path}")
            return config

        except (yaml.YAMLError, ValueError) as e:
            # YAML parsing or validation errors
            logger.error(f"Invalid configuration format in {config_path}: {e}")
            logger.info("Using default configuration")
            return cls()
        except (PermissionError, OSError) as e:
            # File access errors
            logger.error(f"Cannot read configuration file {config_path}: {e}")
            logger.info("Using default configuration")
            return cls()
        except (KeyError, TypeError) as e:
            # Missing or wrong type configuration keys
            logger.error(f"Invalid configuration structure in {config_path}: {e}")
            logger.info("Using default configuration")
            return cls()

    def save_to_yaml(self, config_path: Path):
        """
        Save configuration to YAML file.

        Args:
            config_path: Path to save YAML configuration
        """
        data = {
            'heuristic_weights': {
                'temporal': self.heuristic_weights.temporal,
                'content': self.heuristic_weights.content,
                'structural': self.heuristic_weights.structural,
                'ai': self.heuristic_weights.ai,
            },
            'category_thresholds': {
                'project': self.category_thresholds.project,
                'area': self.category_thresholds.area,
                'resource': self.category_thresholds.resource,
                'archive': self.category_thresholds.archive,
            },
            'keyword_patterns': {
                'project': self.keyword_patterns.project,
                'area': self.keyword_patterns.area,
                'resource': self.keyword_patterns.resource,
                'archive': self.keyword_patterns.archive,
            },
            'temporal_thresholds': {
                'project_max_age': self.temporal_thresholds.project_max_age,
                'area_min_age': self.temporal_thresholds.area_min_age,
                'area_max_age': self.temporal_thresholds.area_max_age,
                'resource_min_age': self.temporal_thresholds.resource_min_age,
                'archive_min_age': self.temporal_thresholds.archive_min_age,
                'archive_min_inactive': self.temporal_thresholds.archive_min_inactive,
            },
            'enable_temporal_heuristic': self.enable_temporal_heuristic,
            'enable_content_heuristic': self.enable_content_heuristic,
            'enable_structural_heuristic': self.enable_structural_heuristic,
            'enable_ai_heuristic': self.enable_ai_heuristic,
            'manual_review_threshold': self.manual_review_threshold,
            'auto_categorize': self.auto_categorize,
            'preserve_user_overrides': self.preserve_user_overrides,
            'default_root': str(self.default_root) if self.default_root else None,
            'project_dir': self.project_dir,
            'area_dir': self.area_dir,
            'resource_dir': self.resource_dir,
            'archive_dir': self.archive_dir,
        }

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Configuration saved to {config_path}")

        except Exception as e:
            logger.error(f"Failed to save config to {config_path}: {e}")

    def get_category_threshold(self, category: PARACategory) -> float:
        """Get threshold for a specific category."""
        thresholds_map = {
            PARACategory.PROJECT: self.category_thresholds.project,
            PARACategory.AREA: self.category_thresholds.area,
            PARACategory.RESOURCE: self.category_thresholds.resource,
            PARACategory.ARCHIVE: self.category_thresholds.archive,
        }
        return thresholds_map.get(category, 0.75)

    def get_category_keywords(self, category: PARACategory) -> List[str]:
        """Get keywords for a specific category."""
        keywords_map = {
            PARACategory.PROJECT: self.keyword_patterns.project,
            PARACategory.AREA: self.keyword_patterns.area,
            PARACategory.RESOURCE: self.keyword_patterns.resource,
            PARACategory.ARCHIVE: self.keyword_patterns.archive,
        }
        return keywords_map.get(category, [])

    def get_category_directory(self, category: PARACategory) -> str:
        """Get directory name for a category."""
        dir_map = {
            PARACategory.PROJECT: self.project_dir,
            PARACategory.AREA: self.area_dir,
            PARACategory.RESOURCE: self.resource_dir,
            PARACategory.ARCHIVE: self.archive_dir,
        }
        return dir_map.get(category, "Unknown")


# Default configuration instance
DEFAULT_CONFIG = PARAConfig()


def load_config(config_path: Optional[Path] = None) -> PARAConfig:
    """
    Load PARA configuration.

    Args:
        config_path: Path to config file (None = use default)

    Returns:
        PARAConfig instance
    """
    if config_path is None:
        # Try to find default config locations
        possible_paths = [
            Path.home() / ".config" / "file-organizer" / "para_config.yaml",
            Path.cwd() / "para_config.yaml",
            Path(__file__).parent / "default_config.yaml",
        ]

        for path in possible_paths:
            if path.exists():
                config_path = path
                break

    if config_path and config_path.exists():
        return PARAConfig.load_from_yaml(config_path)
    else:
        logger.info("Using default PARA configuration")
        # Return a deep copy to prevent callers from mutating the singleton
        return copy.deepcopy(DEFAULT_CONFIG)
