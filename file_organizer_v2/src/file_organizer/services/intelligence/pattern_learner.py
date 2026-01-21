"""
Pattern learning orchestrator module.

Coordinates pattern extraction, confidence scoring, folder learning, and feedback processing
to provide a unified pattern learning system.
"""

from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
import logging

from .pattern_extractor import NamingPatternExtractor
from .confidence import ConfidenceEngine
from .folder_learner import FolderPreferenceLearner
from .feedback_processor import FeedbackProcessor
from .preference_tracker import PreferenceTracker

logger = logging.getLogger(__name__)


class PatternLearner:
    """
    Main orchestrator for pattern learning from user feedback.

    Integrates:
    - Pattern extraction (naming patterns, delimiters, structures)
    - Confidence scoring (frequency, recency, consistency)
    - Folder preference learning
    - Feedback processing (corrections, batch analysis)
    - Preference tracking (from Task #50)
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the pattern learner.

        Args:
            storage_path: Base path for storing learned data
        """
        if storage_path is None:
            storage_path = Path.home() / ".file_organizer"

        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.pattern_extractor = NamingPatternExtractor()
        self.confidence_engine = ConfidenceEngine(
            storage_path=storage_path / "confidence.json"
        )
        self.folder_learner = FolderPreferenceLearner(
            storage_path=storage_path / "folder_prefs.json"
        )
        self.feedback_processor = FeedbackProcessor()
        self.preference_tracker = PreferenceTracker(storage_path=storage_path)

        # Learning state
        self.learning_enabled = True
        self.min_confidence = 0.6

        logger.info("PatternLearner initialized")

    def learn_from_correction(
        self,
        original: Path,
        corrected: Path,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        Learn from a user correction.

        This is the main entry point for real-time learning.

        Args:
            original: Original file path (before correction)
            corrected: Corrected file path (after user modification)
            context: Additional context (operation, suggested action, etc.)

        Returns:
            Dictionary with learning results
        """
        if not self.learning_enabled:
            logger.debug("Learning disabled, skipping correction")
            return {'learning_enabled': False}

        logger.info(f"Learning from correction: {original.name} -> {corrected.name}")

        results = {
            'timestamp': datetime.utcnow().isoformat(),
            'original': str(original),
            'corrected': str(corrected),
            'learned': []
        }

        # Process the correction
        insights = self.feedback_processor.process_correction(
            original, corrected, context
        )

        # Extract and learn naming patterns
        if original.name != corrected.name:
            naming_result = self._learn_naming_pattern(original.name, corrected.name)
            results['learned'].append(naming_result)

        # Learn folder preferences
        if original.parent != corrected.parent:
            folder_result = self._learn_folder_preference(
                original, corrected, context
            )
            results['learned'].append(folder_result)

        # Update preference tracker
        self.preference_tracker.track_operation(
            'correction',
            {'from': str(original), 'to': str(corrected)}
        )

        # Check if retraining needed
        if insights.get('trigger_retraining'):
            self.confidence_engine.recalculate_all()
            results['retraining_triggered'] = True

        logger.info(f"Learned {len(results['learned'])} patterns from correction")

        return results

    def extract_naming_pattern(self, filenames: List[str]) -> Dict:
        """
        Extract common naming patterns from a list of filenames.

        Args:
            filenames: List of filenames to analyze

        Returns:
            Dictionary with extracted patterns
        """
        if not filenames:
            return {'patterns': []}

        patterns = {
            'common_elements': [],
            'structure': {},
            'delimiters': {},
            'case_style': None,
            'confidence': 0.0
        }

        # Extract common elements
        patterns['common_elements'] = self.pattern_extractor.extract_common_elements(
            filenames
        )

        # Identify structure pattern
        patterns['structure'] = self.pattern_extractor.identify_structure_pattern(
            filenames
        )

        # Analyze delimiters
        delimiter_counts = {}
        for filename in filenames:
            delims = self.pattern_extractor.extract_delimiters(filename)
            for d in delims:
                delimiter_counts[d] = delimiter_counts.get(d, 0) + 1

        patterns['delimiters'] = delimiter_counts

        # Detect common case style
        case_styles = [
            self.pattern_extractor.detect_case_style(f)
            for f in filenames
        ]
        if case_styles:
            patterns['case_style'] = max(set(case_styles), key=case_styles.count)

        # Calculate confidence based on consistency
        consistency = len(patterns['common_elements']) / max(len(filenames), 1)
        patterns['confidence'] = consistency

        return patterns

    def identify_folder_preference(
        self,
        file_type: str,
        chosen_folder: Path,
        context: Optional[Dict] = None
    ) -> None:
        """
        Record a folder choice for learning.

        Args:
            file_type: File extension
            chosen_folder: Folder path chosen by user
            context: Additional context
        """
        self.folder_learner.track_folder_choice(
            file_type, chosen_folder, context
        )

        logger.debug(f"Tracked folder preference: {file_type} -> {chosen_folder}")

    def update_confidence(self, pattern_id: str, success: bool) -> None:
        """
        Update confidence score for a pattern based on success/failure.

        Args:
            pattern_id: Pattern identifier
            success: Whether the pattern application was successful
        """
        self.confidence_engine.update_pattern_confidence(pattern_id, success)

        logger.debug(f"Updated confidence for {pattern_id}: success={success}")

    def get_pattern_suggestion(
        self,
        file_info: Dict,
        min_confidence: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Get pattern-based suggestions for a file.

        Args:
            file_info: File information (name, type, etc.)
            min_confidence: Minimum confidence threshold (default: self.min_confidence)

        Returns:
            Suggestion dictionary or None if no confident suggestion
        """
        if min_confidence is None:
            min_confidence = self.min_confidence

        suggestion = {
            'naming': None,
            'folder': None,
            'confidence': 0.0
        }

        # Get naming suggestion
        if 'name' in file_info:
            naming_patterns = self._get_naming_suggestions(file_info['name'])
            if naming_patterns and naming_patterns['confidence'] >= min_confidence:
                suggestion['naming'] = naming_patterns

        # Get folder suggestion
        if 'type' in file_info:
            folder = self.folder_learner.suggest_folder_structure(
                file_info, min_confidence
            )
            if folder:
                confidence = self.folder_learner.get_folder_confidence(
                    file_info['type'], folder
                )
                suggestion['folder'] = {
                    'path': str(folder),
                    'confidence': confidence
                }

        # Calculate overall confidence
        confidences = []
        if suggestion['naming']:
            confidences.append(suggestion['naming']['confidence'])
        if suggestion['folder']:
            confidences.append(suggestion['folder']['confidence'])

        if confidences:
            suggestion['confidence'] = sum(confidences) / len(confidences)

        # Return only if we have suggestions with sufficient confidence
        if suggestion['confidence'] >= min_confidence:
            return suggestion

        return None

    def get_learning_stats(self) -> Dict:
        """
        Get statistics about learned patterns.

        Returns:
            Dictionary with learning statistics
        """
        stats = {
            'timestamp': datetime.utcnow().isoformat(),
            'confidence_stats': self.confidence_engine.get_stats(),
            'folder_stats': self.folder_learner.analyze_organization_patterns(),
            'correction_count': self.feedback_processor.correction_count,
            'learning_enabled': self.learning_enabled
        }

        return stats

    def batch_learn_from_history(
        self,
        corrections: List[Dict],
        max_age_days: Optional[int] = None
    ) -> Dict:
        """
        Learn from historical corrections in batch.

        Args:
            corrections: List of correction records
            max_age_days: Only process recent corrections (optional)

        Returns:
            Batch learning results
        """
        logger.info(f"Batch learning from {len(corrections)} corrections")

        results = self.feedback_processor.batch_process_history(
            corrections, max_age_days
        )

        # Apply learned patterns
        for pattern in results.get('name_patterns', []):
            if pattern['pattern_type'] == 'preferred_delimiter':
                # Store as a learned pattern
                pass  # Would integrate with pattern storage

        for pattern in results.get('folder_patterns', []):
            if pattern['pattern_type'] == 'type_folder_preference':
                # Already tracked through folder_learner
                pass

        # Trigger full confidence recalculation
        self.confidence_engine.recalculate_all()

        return results

    def clear_old_patterns(self, days: int = 90) -> Dict:
        """
        Clear patterns older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Dictionary with clearing results
        """
        results = {
            'folder_preferences_cleared': 0,
            'patterns_decayed': 0
        }

        # Clear old folder preferences
        results['folder_preferences_cleared'] = \
            self.folder_learner.clear_old_preferences(days)

        # Apply decay to old patterns
        results['patterns_decayed'] = \
            self.confidence_engine.decay_old_patterns(days)

        logger.info(f"Cleared {results['folder_preferences_cleared']} old preferences")

        return results

    def enable_learning(self) -> None:
        """Enable pattern learning."""
        self.learning_enabled = True
        logger.info("Pattern learning enabled")

    def disable_learning(self) -> None:
        """Disable pattern learning."""
        self.learning_enabled = False
        logger.info("Pattern learning disabled")

    def _learn_naming_pattern(
        self,
        original_name: str,
        corrected_name: str
    ) -> Dict:
        """
        Learn from a naming correction.

        Args:
            original_name: Original filename
            corrected_name: Corrected filename

        Returns:
            Learning result dictionary
        """
        result = {
            'type': 'naming',
            'patterns': []
        }

        # Analyze the correction
        orig_info = self.pattern_extractor.analyze_filename(original_name)
        corr_info = self.pattern_extractor.analyze_filename(corrected_name)

        # Learn delimiter preference
        if orig_info['delimiters'] != corr_info['delimiters']:
            result['patterns'].append({
                'pattern_type': 'delimiter',
                'value': corr_info['delimiters']
            })

        # Learn case style preference
        if orig_info['case_style'] != corr_info['case_style']:
            result['patterns'].append({
                'pattern_type': 'case_style',
                'value': corr_info['case_style']
            })

        # Learn structure pattern
        if corr_info.get('structure'):
            result['patterns'].append({
                'pattern_type': 'structure',
                'value': corr_info['structure']
            })

        return result

    def _learn_folder_preference(
        self,
        original: Path,
        corrected: Path,
        context: Optional[Dict]
    ) -> Dict:
        """
        Learn from a folder correction.

        Args:
            original: Original path
            corrected: Corrected path
            context: Additional context

        Returns:
            Learning result dictionary
        """
        result = {
            'type': 'folder',
            'file_type': original.suffix.lower(),
            'from': str(original.parent),
            'to': str(corrected.parent)
        }

        # Track the folder choice
        self.folder_learner.track_folder_choice(
            original.suffix.lower(),
            corrected.parent,
            context
        )

        # Get updated confidence
        result['confidence'] = self.folder_learner.get_folder_confidence(
            original.suffix.lower(),
            corrected.parent
        )

        return result

    def _get_naming_suggestions(self, filename: str) -> Optional[Dict]:
        """
        Get naming pattern suggestions for a filename.

        Args:
            filename: Current filename

        Returns:
            Naming suggestions or None
        """
        # Analyze current filename
        info = self.pattern_extractor.analyze_filename(filename)

        # Get suggested convention
        suggested = self.pattern_extractor.suggest_naming_convention(info)

        if suggested:
            return {
                'suggested_name': suggested,
                'confidence': 0.7,  # Base confidence
                'reason': 'Based on learned patterns'
            }

        return None
