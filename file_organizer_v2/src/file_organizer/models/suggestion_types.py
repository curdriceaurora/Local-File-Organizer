"""
Suggestion Types and Data Models

Defines the data structures for smart suggestions.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
from enum import Enum


class SuggestionType(Enum):
    """Types of suggestions the system can make."""
    MOVE = "move"
    RENAME = "rename"
    TAG = "tag"
    RESTRUCTURE = "restructure"
    DELETE = "delete"
    MERGE = "merge"


class ConfidenceLevel(Enum):
    """Confidence level categories."""
    VERY_LOW = "very_low"     # 0-20%
    LOW = "low"               # 20-40%
    MEDIUM = "medium"         # 40-60%
    HIGH = "high"             # 60-80%
    VERY_HIGH = "very_high"   # 80-100%


@dataclass
class Suggestion:
    """
    Represents a single organizational suggestion.
    """
    suggestion_id: str
    suggestion_type: SuggestionType
    file_path: Path
    target_path: Optional[Path] = None
    confidence: float = 0.0  # 0-100
    reasoning: str = ""
    metadata: Dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    # Additional attributes for specific suggestion types
    tags: List[str] = field(default_factory=list)
    new_name: Optional[str] = None
    related_files: List[Path] = field(default_factory=list)

    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Get the confidence level category."""
        if self.confidence >= 80:
            return ConfidenceLevel.VERY_HIGH
        elif self.confidence >= 60:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 40:
            return ConfidenceLevel.MEDIUM
        elif self.confidence >= 20:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW

    def to_dict(self) -> Dict:
        """Convert suggestion to dictionary."""
        return {
            'suggestion_id': self.suggestion_id,
            'suggestion_type': self.suggestion_type.value,
            'file_path': str(self.file_path),
            'target_path': str(self.target_path) if self.target_path else None,
            'confidence': self.confidence,
            'confidence_level': self.confidence_level.value,
            'reasoning': self.reasoning,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'tags': self.tags,
            'new_name': self.new_name,
            'related_files': [str(f) for f in self.related_files]
        }


@dataclass
class SuggestionBatch:
    """A batch of related suggestions."""
    batch_id: str
    suggestions: List[Suggestion]
    category: str
    description: str
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def avg_confidence(self) -> float:
        """Average confidence across all suggestions."""
        if not self.suggestions:
            return 0.0
        return sum(s.confidence for s in self.suggestions) / len(self.suggestions)

    @property
    def total_suggestions(self) -> int:
        """Total number of suggestions in batch."""
        return len(self.suggestions)

    def to_dict(self) -> Dict:
        """Convert batch to dictionary."""
        return {
            'batch_id': self.batch_id,
            'suggestions': [s.to_dict() for s in self.suggestions],
            'category': self.category,
            'description': self.description,
            'avg_confidence': self.avg_confidence,
            'total_suggestions': self.total_suggestions,
            'created_at': self.created_at.isoformat()
        }


@dataclass
class ConfidenceFactors:
    """
    Factors contributing to confidence score.
    """
    pattern_strength: float = 0.0      # How strong the detected pattern is
    content_similarity: float = 0.0    # Similarity to target location content
    user_history: float = 0.0          # Based on past user actions
    naming_convention: float = 0.0     # Matches naming patterns
    file_type_match: float = 0.0       # File type appropriate for location
    recency: float = 0.0               # How recent the file is
    size_appropriateness: float = 0.0  # File size appropriate for location

    # Weights for each factor (should sum to 1.0)
    weights: Dict[str, float] = field(default_factory=lambda: {
        'pattern_strength': 0.25,
        'content_similarity': 0.20,
        'user_history': 0.15,
        'naming_convention': 0.15,
        'file_type_match': 0.15,
        'recency': 0.05,
        'size_appropriateness': 0.05
    })

    def calculate_weighted_score(self) -> float:
        """Calculate weighted confidence score."""
        score = (
            self.pattern_strength * self.weights['pattern_strength'] +
            self.content_similarity * self.weights['content_similarity'] +
            self.user_history * self.weights['user_history'] +
            self.naming_convention * self.weights['naming_convention'] +
            self.file_type_match * self.weights['file_type_match'] +
            self.recency * self.weights['recency'] +
            self.size_appropriateness * self.weights['size_appropriateness']
        )
        return min(max(score, 0.0), 100.0)  # Clamp to 0-100

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'pattern_strength': self.pattern_strength,
            'content_similarity': self.content_similarity,
            'user_history': self.user_history,
            'naming_convention': self.naming_convention,
            'file_type_match': self.file_type_match,
            'recency': self.recency,
            'size_appropriateness': self.size_appropriateness,
            'weighted_score': self.calculate_weighted_score(),
            'weights': self.weights
        }
