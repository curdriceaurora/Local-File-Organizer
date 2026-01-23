"""
PARA Rule Engine Implementation

Provides interfaces and data structures for the PARA categorization rule engine.
This is a design specification - actual implementation will be in subsequent tasks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime


class ConditionType(Enum):
    """Types of conditions that can be evaluated in rules."""
    CONTENT_KEYWORD = "content_keyword"
    FILENAME_PATTERN = "filename_pattern"
    PATH_CONTAINS = "path_contains"
    FILE_EXTENSION = "file_extension"
    TEMPORAL = "temporal"
    FILE_SIZE = "file_size"
    METADATA = "metadata"
    AI_ANALYSIS = "ai_analysis"
    MODIFICATION_FREQUENCY = "modification_frequency"
    COMPOSITE = "composite"  # AND, OR, NOT combinations


class ActionType(Enum):
    """Types of actions that can be executed by rules."""
    CATEGORIZE = "categorize"
    SUGGEST = "suggest"
    FLAG_REVIEW = "flag_review"
    ADD_TAG = "add_tag"
    SET_CONFIDENCE = "set_confidence"


class LogicalOperator(Enum):
    """Logical operators for combining conditions."""
    AND = "and"
    OR = "or"
    NOT = "not"


class ConflictResolutionStrategy(Enum):
    """Strategies for resolving conflicts when multiple rules match."""
    HIGHEST_CONFIDENCE = "highest_confidence"
    PRIORITY_BASED = "priority_based"
    CONFIDENCE_WEIGHTED_VOTING = "confidence_weighted_voting"
    USER_PREFERENCE = "user_preference"
    MANUAL_REVIEW = "manual_review"


@dataclass
class RuleCondition:
    """
    Represents a single condition in a rule.
    
    Attributes:
        type: The type of condition to evaluate
        operator: Logical operator if combining multiple conditions
        values: Values to check against (keywords, patterns, etc.)
        threshold: Numeric threshold for quantitative conditions
        min_matches: Minimum number of matches required
        max_matches: Maximum number of matches allowed
        subconditions: Nested conditions for composite logic
        metadata: Additional configuration for the condition
    """
    type: ConditionType
    operator: Optional[LogicalOperator] = None
    values: Optional[List[str]] = None
    threshold: Optional[float] = None
    min_matches: Optional[int] = None
    max_matches: Optional[int] = None
    subconditions: Optional[List['RuleCondition']] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate condition configuration."""
        if self.type == ConditionType.COMPOSITE and not self.subconditions:
            raise ValueError("Composite conditions must have subconditions")
        if self.type != ConditionType.COMPOSITE and not self.values and self.threshold is None:
            raise ValueError(f"Condition type {self.type} requires values or threshold")


@dataclass
class RuleAction:
    """
    Represents an action to be taken when a rule matches.
    
    Attributes:
        type: The type of action to execute
        category: PARA category to assign (for categorize/suggest actions)
        confidence: Confidence score for this categorization (0.0-1.0)
        tags: Tags to add to the file
        reason: Human-readable reason for this action
        metadata: Additional action configuration
    """
    type: ActionType
    category: Optional[str] = None
    confidence: Optional[float] = None
    tags: Optional[List[str]] = None
    reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate action configuration."""
        if self.type in [ActionType.CATEGORIZE, ActionType.SUGGEST]:
            if not self.category:
                raise ValueError(f"Action type {self.type} requires a category")
            if self.confidence is None:
                raise ValueError(f"Action type {self.type} requires a confidence score")
            if not 0.0 <= self.confidence <= 1.0:
                raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")


@dataclass
class Rule:
    """
    Represents a complete rule for PARA categorization.
    
    Attributes:
        name: Unique identifier for the rule
        description: Human-readable description of what the rule does
        priority: Priority for conflict resolution (higher = more important)
        enabled: Whether this rule is active
        conditions: List of conditions that must be met
        actions: Actions to execute when conditions are met
        metadata: Additional rule metadata (author, created date, etc.)
    """
    name: str
    description: str
    priority: int
    conditions: List[RuleCondition]
    actions: List[RuleAction]
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate rule configuration."""
        if not self.conditions:
            raise ValueError("Rule must have at least one condition")
        if not self.actions:
            raise ValueError("Rule must have at least one action")
        if self.priority < 0:
            raise ValueError("Priority must be non-negative")


@dataclass
class EvaluationContext:
    """
    Context information for evaluating rules against a file.
    
    Attributes:
        file_path: Path to the file being evaluated
        content: Text content of the file (if applicable)
        file_stat: File system statistics
        metadata: Additional metadata about the file
        ai_analysis: Results from AI analysis (if available)
        user_preferences: User-specific preferences
    """
    file_path: Path
    content: Optional[str] = None
    file_stat: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    ai_analysis: Optional[Dict[str, Any]] = None
    user_preferences: Optional[Dict[str, Any]] = None

    @property
    def file_extension(self) -> str:
        """Get the file extension."""
        return self.file_path.suffix.lower()

    @property
    def file_name(self) -> str:
        """Get the file name without path."""
        return self.file_path.name

    @property
    def file_age_days(self) -> Optional[int]:
        """Calculate file age in days."""
        if not self.file_stat or 'created' not in self.file_stat:
            return None
        created = self.file_stat['created']
        if isinstance(created, datetime):
            return (datetime.now() - created).days
        return None


@dataclass
class RuleMatchResult:
    """
    Result of evaluating a rule against a file.
    
    Attributes:
        rule: The rule that was evaluated
        matched: Whether the rule conditions were satisfied
        confidence: Confidence score from the rule (if matched)
        category: Suggested category (if matched)
        reasons: List of reasons why the rule matched/didn't match
        condition_results: Detailed results for each condition
        execution_time_ms: Time taken to evaluate the rule
    """
    rule: Rule
    matched: bool
    confidence: Optional[float] = None
    category: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    condition_results: Dict[str, bool] = field(default_factory=dict)
    execution_time_ms: float = 0.0


class RuleParser(ABC):
    """
    Abstract interface for parsing rule definitions from various formats.
    
    The parser converts external rule definitions (YAML, JSON, etc.) into
    internal Rule objects that can be evaluated by the engine.
    """

    @abstractmethod
    def parse_file(self, file_path: Path) -> List[Rule]:
        """
        Parse rules from a file.
        
        Args:
            file_path: Path to the rule definition file
            
        Returns:
            List of parsed Rule objects
            
        Raises:
            ValueError: If the file format is invalid
            FileNotFoundError: If the file doesn't exist
        """
        pass

    @abstractmethod
    def parse_string(self, content: str) -> List[Rule]:
        """
        Parse rules from a string.
        
        Args:
            content: Rule definition as a string
            
        Returns:
            List of parsed Rule objects
            
        Raises:
            ValueError: If the content format is invalid
        """
        pass

    @abstractmethod
    def validate_rule(self, rule: Rule) -> bool:
        """
        Validate that a rule is properly configured.
        
        Args:
            rule: Rule to validate
            
        Returns:
            True if valid, raises exception otherwise
            
        Raises:
            ValueError: If the rule is invalid with detailed error message
        """
        pass


class ConditionEvaluator(ABC):
    """
    Abstract interface for evaluating rule conditions.
    
    The evaluator checks whether a file meets the conditions specified in a rule.
    """

    @abstractmethod
    def evaluate_condition(
        self, 
        condition: RuleCondition, 
        context: EvaluationContext
    ) -> bool:
        """
        Evaluate a single condition against a file.
        
        Args:
            condition: The condition to evaluate
            context: Context information about the file
            
        Returns:
            True if the condition is satisfied, False otherwise
        """
        pass

    @abstractmethod
    def evaluate_composite(
        self,
        conditions: List[RuleCondition],
        operator: LogicalOperator,
        context: EvaluationContext
    ) -> bool:
        """
        Evaluate multiple conditions with a logical operator.
        
        Args:
            conditions: List of conditions to evaluate
            operator: How to combine the results (AND, OR, NOT)
            context: Context information about the file
            
        Returns:
            Combined result based on the operator
        """
        pass

    @abstractmethod
    def get_match_score(
        self,
        condition: RuleCondition,
        context: EvaluationContext
    ) -> float:
        """
        Get a numeric score for how well a condition matches (0.0-1.0).
        
        This is useful for confidence scoring and partial matching.
        
        Args:
            condition: The condition to score
            context: Context information about the file
            
        Returns:
            Score between 0.0 (no match) and 1.0 (perfect match)
        """
        pass


class ActionExecutor(ABC):
    """
    Abstract interface for executing rule actions.
    
    The executor performs the actions specified by matched rules.
    """

    @abstractmethod
    def execute_action(
        self,
        action: RuleAction,
        context: EvaluationContext
    ) -> Dict[str, Any]:
        """
        Execute a single action.
        
        Args:
            action: The action to execute
            context: Context information about the file
            
        Returns:
            Result of the action execution with details
        """
        pass

    @abstractmethod
    def can_execute(
        self,
        action: RuleAction,
        context: EvaluationContext
    ) -> bool:
        """
        Check if an action can be executed in the current context.
        
        Args:
            action: The action to check
            context: Context information
            
        Returns:
            True if the action can be executed
        """
        pass


class ConflictResolver(ABC):
    """
    Abstract interface for resolving conflicts when multiple rules match.
    
    The resolver determines which category to assign when multiple rules
    suggest different categories.
    """

    @abstractmethod
    def resolve(
        self,
        matches: List[RuleMatchResult],
        strategy: ConflictResolutionStrategy,
        context: EvaluationContext
    ) -> RuleMatchResult:
        """
        Resolve conflicts between multiple matching rules.
        
        Args:
            matches: List of rules that matched
            strategy: Strategy to use for resolution
            context: Context information about the file
            
        Returns:
            The winning rule match result
        """
        pass

    @abstractmethod
    def should_flag_for_review(
        self,
        matches: List[RuleMatchResult],
        threshold: float
    ) -> bool:
        """
        Determine if the categorization should be flagged for manual review.
        
        Args:
            matches: List of rules that matched
            threshold: Confidence threshold below which to flag
            
        Returns:
            True if the result should be reviewed manually
        """
        pass


class CategoryScorer(ABC):
    """
    Abstract interface for calculating confidence scores for categories.
    
    The scorer combines multiple signals (heuristics, rules, AI) to produce
    a final confidence score for each category.
    """

    @abstractmethod
    def calculate_category_scores(
        self,
        matches: List[RuleMatchResult],
        context: EvaluationContext
    ) -> Dict[str, float]:
        """
        Calculate confidence scores for all categories.
        
        Args:
            matches: List of rules that matched
            context: Context information about the file
            
        Returns:
            Dictionary mapping category names to confidence scores (0.0-1.0)
        """
        pass

    @abstractmethod
    def get_best_category(
        self,
        scores: Dict[str, float],
        threshold: float
    ) -> Optional[str]:
        """
        Get the best category based on scores.
        
        Args:
            scores: Category confidence scores
            threshold: Minimum confidence threshold
            
        Returns:
            Best category name or None if no category meets threshold
        """
        pass

    @abstractmethod
    def calculate_overall_confidence(
        self,
        matches: List[RuleMatchResult],
        heuristic_scores: Optional[Dict[str, float]] = None
    ) -> float:
        """
        Calculate an overall confidence score for the categorization.
        
        Args:
            matches: List of rules that matched
            heuristic_scores: Additional scores from heuristics
            
        Returns:
            Overall confidence score (0.0-1.0)
        """
        pass


class RuleEngine:
    """
    Main rule engine orchestrator.
    
    Coordinates rule parsing, condition evaluation, action execution,
    and conflict resolution to categorize files using the PARA methodology.
    """

    def __init__(
        self,
        parser: RuleParser,
        evaluator: ConditionEvaluator,
        executor: ActionExecutor,
        resolver: ConflictResolver,
        scorer: CategoryScorer
    ):
        """
        Initialize the rule engine with its components.
        
        Args:
            parser: Rule parser implementation
            evaluator: Condition evaluator implementation
            executor: Action executor implementation
            resolver: Conflict resolver implementation
            scorer: Category scorer implementation
        """
        self.parser = parser
        self.evaluator = evaluator
        self.executor = executor
        self.resolver = resolver
        self.scorer = scorer
        self.rules: List[Rule] = []

    def load_rules(self, rule_file: Path) -> int:
        """
        Load rules from a file.
        
        Args:
            rule_file: Path to the rule definition file
            
        Returns:
            Number of rules loaded
        """
        self.rules = self.parser.parse_file(rule_file)
        return len(self.rules)

    def add_rule(self, rule: Rule) -> None:
        """
        Add a single rule to the engine.
        
        Args:
            rule: Rule to add
        """
        if self.parser.validate_rule(rule):
            self.rules.append(rule)

    def evaluate_file(
        self,
        context: EvaluationContext,
        strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.HIGHEST_CONFIDENCE
    ) -> Optional[RuleMatchResult]:
        """
        Evaluate all rules against a file and return the best match.
        
        Args:
            context: Context information about the file
            strategy: Strategy for resolving conflicts
            
        Returns:
            Best matching rule result or None if no rules match
        """
        matches = []
        
        for rule in self.rules:
            if not rule.enabled:
                continue
                
            # Evaluate all conditions
            all_conditions_met = True
            for condition in rule.conditions:
                if not self.evaluator.evaluate_condition(condition, context):
                    all_conditions_met = False
                    break
            
            if all_conditions_met:
                # Extract confidence and category from actions
                confidence = None
                category = None
                for action in rule.actions:
                    if action.type in [ActionType.CATEGORIZE, ActionType.SUGGEST]:
                        confidence = action.confidence
                        category = action.category
                        break
                
                match = RuleMatchResult(
                    rule=rule,
                    matched=True,
                    confidence=confidence,
                    category=category
                )
                matches.append(match)
        
        if not matches:
            return None
        
        if len(matches) == 1:
            return matches[0]
        
        # Resolve conflicts
        return self.resolver.resolve(matches, strategy, context)

    def get_category_scores(
        self,
        context: EvaluationContext
    ) -> Dict[str, float]:
        """
        Get confidence scores for all categories.
        
        Args:
            context: Context information about the file
            
        Returns:
            Dictionary mapping category names to confidence scores
        """
        matches = []
        
        for rule in self.rules:
            if not rule.enabled:
                continue
                
            all_conditions_met = all(
                self.evaluator.evaluate_condition(cond, context)
                for cond in rule.conditions
            )
            
            if all_conditions_met:
                matches.append(RuleMatchResult(rule=rule, matched=True))
        
        return self.scorer.calculate_category_scores(matches, context)