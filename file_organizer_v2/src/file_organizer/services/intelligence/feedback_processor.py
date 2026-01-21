"""
Feedback processing module.

Processes user corrections and feedback to update pattern learning models in real-time.
Supports both individual corrections and batch history analysis.
"""

from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FeedbackProcessor:
    """
    Processes user feedback and corrections to improve pattern learning.

    Features:
    - Real-time correction processing
    - Batch correction history analysis
    - Incremental learning updates
    - Learning event triggers
    """

    def __init__(self):
        """Initialize the feedback processor."""
        self.correction_count = 0
        self.batch_processing_enabled = True
        self.learning_threshold = 5  # Trigger retraining after N corrections

    def process_correction(
        self,
        original: Path,
        corrected: Path,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        Process a single user correction in real-time.

        Args:
            original: Original file path (before correction)
            corrected: Corrected file path (after user edit)
            context: Additional context (operation type, timestamp, etc.)

        Returns:
            Dictionary with extracted learning insights
        """
        insights = {
            'timestamp': datetime.utcnow().isoformat(),
            'original_path': str(original),
            'corrected_path': str(corrected),
            'learning_signals': []
        }

        # Analyze file name change
        if original.name != corrected.name:
            name_insight = self._analyze_name_correction(original.name, corrected.name)
            insights['learning_signals'].append(name_insight)
            logger.debug(f"Name correction: {original.name} -> {corrected.name}")

        # Analyze folder change
        if original.parent != corrected.parent:
            folder_insight = self._analyze_folder_correction(
                original, corrected, context
            )
            insights['learning_signals'].append(folder_insight)
            logger.debug(f"Folder correction: {original.parent} -> {corrected.parent}")

        # Extract patterns from context
        if context:
            context_insight = self._extract_context_patterns(context)
            if context_insight:
                insights['learning_signals'].append(context_insight)

        self.correction_count += 1

        # Check if retraining should be triggered
        if self.correction_count >= self.learning_threshold:
            insights['trigger_retraining'] = True
            logger.info(f"Retraining triggered after {self.correction_count} corrections")

        return insights

    def batch_process_history(
        self,
        corrections: List[Dict],
        max_age_days: Optional[int] = None
    ) -> Dict:
        """
        Process historical corrections in batch to extract patterns.

        Args:
            corrections: List of correction records
            max_age_days: Only process corrections within this age (optional)

        Returns:
            Aggregated learning insights
        """
        from datetime import timedelta

        if max_age_days:
            cutoff = datetime.utcnow() - timedelta(days=max_age_days)
            corrections = [
                c for c in corrections
                if datetime.fromisoformat(c.get('timestamp', '1970-01-01'))
                > cutoff
            ]

        logger.info(f"Batch processing {len(corrections)} corrections")

        insights = {
            'processed_count': len(corrections),
            'name_patterns': [],
            'folder_patterns': [],
            'common_operations': {},
            'timestamp': datetime.utcnow().isoformat()
        }

        # Aggregate naming patterns
        name_changes = []
        folder_changes = []

        for correction in corrections:
            original = Path(correction.get('original_path', ''))
            corrected = Path(correction.get('corrected_path', ''))

            if original.name != corrected.name:
                name_changes.append((original.name, corrected.name))

            if original.parent != corrected.parent:
                folder_changes.append((
                    str(original.parent),
                    str(corrected.parent),
                    original.suffix.lower()
                ))

        # Analyze naming patterns
        if name_changes:
            insights['name_patterns'] = self._extract_batch_name_patterns(name_changes)

        # Analyze folder patterns
        if folder_changes:
            insights['folder_patterns'] = self._extract_batch_folder_patterns(folder_changes)

        # Identify common operations
        insights['common_operations'] = self._identify_common_operations(corrections)

        return insights

    def update_learning_model(self, insights: Dict) -> bool:
        """
        Update the learning model with new insights.

        Args:
            insights: Learning insights from correction processing

        Returns:
            True if update successful
        """
        # This would integrate with pattern learner
        # For now, just validate and log
        if not insights or 'learning_signals' not in insights:
            logger.warning("No learning signals in insights")
            return False

        signal_count = len(insights['learning_signals'])
        logger.info(f"Updating learning model with {signal_count} signals")

        return True

    def trigger_retraining(self) -> Dict:
        """
        Trigger a full model retraining.

        Returns:
            Retraining status and metrics
        """
        logger.info("Triggering pattern learning retraining")

        status = {
            'triggered_at': datetime.utcnow().isoformat(),
            'correction_count': self.correction_count,
            'status': 'queued'
        }

        # Reset counter after triggering
        self.correction_count = 0

        return status

    def _analyze_name_correction(
        self,
        original_name: str,
        corrected_name: str
    ) -> Dict:
        """
        Analyze a filename correction to extract patterns.

        Args:
            original_name: Original filename
            corrected_name: Corrected filename

        Returns:
            Dictionary with naming pattern insights
        """
        insight = {
            'type': 'naming',
            'original': original_name,
            'corrected': corrected_name,
            'patterns': []
        }

        # Detect delimiter changes
        orig_delimiters = self._extract_delimiters(original_name)
        corr_delimiters = self._extract_delimiters(corrected_name)

        if orig_delimiters != corr_delimiters:
            insight['patterns'].append({
                'pattern_type': 'delimiter_change',
                'from': orig_delimiters,
                'to': corr_delimiters
            })

        # Detect case changes
        if original_name.lower() == corrected_name.lower():
            insight['patterns'].append({
                'pattern_type': 'case_change',
                'from': self._detect_case_style(original_name),
                'to': self._detect_case_style(corrected_name)
            })

        # Detect prefix/suffix additions
        orig_base = Path(original_name).stem
        corr_base = Path(corrected_name).stem

        if corr_base.startswith(orig_base):
            suffix = corr_base[len(orig_base):]
            insight['patterns'].append({
                'pattern_type': 'suffix_addition',
                'suffix': suffix
            })
        elif corr_base.endswith(orig_base):
            prefix = corr_base[:-len(orig_base)]
            insight['patterns'].append({
                'pattern_type': 'prefix_addition',
                'prefix': prefix
            })

        return insight

    def _analyze_folder_correction(
        self,
        original: Path,
        corrected: Path,
        context: Optional[Dict]
    ) -> Dict:
        """
        Analyze a folder correction.

        Args:
            original: Original path
            corrected: Corrected path
            context: Additional context

        Returns:
            Folder pattern insights
        """
        insight = {
            'type': 'folder',
            'file_type': original.suffix.lower(),
            'from_folder': str(original.parent),
            'to_folder': str(corrected.parent),
            'patterns': []
        }

        # Check if it's a categorization change
        if context and 'category' in context:
            insight['patterns'].append({
                'pattern_type': 'category_change',
                'category': context['category']
            })

        # Check for project-based organization
        from_parts = original.parent.parts
        to_parts = corrected.parent.parts

        # Find common ancestor and divergence point
        common_depth = 0
        for i, (f, t) in enumerate(zip(from_parts, to_parts)):
            if f == t:
                common_depth = i + 1
            else:
                break

        if common_depth < len(to_parts):
            insight['patterns'].append({
                'pattern_type': 'subfolder_structure',
                'depth': len(to_parts) - common_depth,
                'structure': '/'.join(to_parts[common_depth:])
            })

        return insight

    def _extract_context_patterns(self, context: Dict) -> Optional[Dict]:
        """
        Extract patterns from context information.

        Args:
            context: Context dictionary

        Returns:
            Context-based patterns or None
        """
        if not context:
            return None

        patterns = []

        # Check for operation type patterns
        if 'operation' in context:
            patterns.append({
                'pattern_type': 'operation',
                'value': context['operation']
            })

        # Check for suggested action vs actual
        if 'suggested' in context and 'actual' in context:
            if context['suggested'] != context['actual']:
                patterns.append({
                    'pattern_type': 'suggestion_override',
                    'suggested': context['suggested'],
                    'actual': context['actual']
                })

        if patterns:
            return {
                'type': 'context',
                'patterns': patterns
            }

        return None

    def _extract_batch_name_patterns(
        self,
        name_changes: List[tuple]
    ) -> List[Dict]:
        """
        Extract common naming patterns from batch changes.

        Args:
            name_changes: List of (original, corrected) name tuples

        Returns:
            List of common patterns
        """
        patterns = []

        # Find common delimiter preferences
        delimiters = {}
        for _, corrected in name_changes:
            delims = self._extract_delimiters(corrected)
            for d in delims:
                delimiters[d] = delimiters.get(d, 0) + 1

        if delimiters:
            most_common = max(delimiters.items(), key=lambda x: x[1])
            patterns.append({
                'pattern_type': 'preferred_delimiter',
                'delimiter': most_common[0],
                'frequency': most_common[1]
            })

        # Find common case styles
        case_styles = {}
        for _, corrected in name_changes:
            style = self._detect_case_style(corrected)
            case_styles[style] = case_styles.get(style, 0) + 1

        if case_styles:
            most_common = max(case_styles.items(), key=lambda x: x[1])
            patterns.append({
                'pattern_type': 'preferred_case',
                'style': most_common[0],
                'frequency': most_common[1]
            })

        return patterns

    def _extract_batch_folder_patterns(
        self,
        folder_changes: List[tuple]
    ) -> List[Dict]:
        """
        Extract common folder patterns from batch changes.

        Args:
            folder_changes: List of (from_folder, to_folder, file_type) tuples

        Returns:
            List of common patterns
        """
        patterns = []

        # Group by file type
        type_mappings = {}
        for from_folder, to_folder, file_type in folder_changes:
            if file_type not in type_mappings:
                type_mappings[file_type] = {}
            type_mappings[file_type][to_folder] = \
                type_mappings[file_type].get(to_folder, 0) + 1

        # Find strong preferences (>60% of moves for a type)
        for file_type, folders in type_mappings.items():
            total = sum(folders.values())
            for folder, count in folders.items():
                if count / total > 0.6:
                    patterns.append({
                        'pattern_type': 'type_folder_preference',
                        'file_type': file_type,
                        'folder': folder,
                        'confidence': count / total,
                        'count': count
                    })

        return patterns

    def _identify_common_operations(
        self,
        corrections: List[Dict]
    ) -> Dict:
        """
        Identify common correction operations.

        Args:
            corrections: List of correction records

        Returns:
            Dictionary of operation frequencies
        """
        operations = {}

        for correction in corrections:
            op_type = correction.get('operation', 'unknown')
            operations[op_type] = operations.get(op_type, 0) + 1

        return operations

    @staticmethod
    def _extract_delimiters(filename: str) -> List[str]:
        """Extract delimiter characters from a filename."""
        delimiters = []
        for char in filename:
            if char in ['_', '-', '.', ' ']:
                if char not in delimiters:
                    delimiters.append(char)
        return delimiters

    @staticmethod
    def _detect_case_style(filename: str) -> str:
        """Detect the case style of a filename."""
        stem = Path(filename).stem

        if stem.islower():
            return 'lowercase'
        elif stem.isupper():
            return 'uppercase'
        elif '_' in stem and stem.replace('_', '').islower():
            return 'snake_case'
        elif '-' in stem and stem.replace('-', '').islower():
            return 'kebab-case'
        elif stem[0].isupper() and ' ' in stem:
            return 'title_case'
        elif stem[0].islower() and any(c.isupper() for c in stem[1:]):
            return 'camelCase'
        elif stem[0].isupper() and any(c.isupper() for c in stem[1:]):
            return 'PascalCase'

        return 'mixed'
