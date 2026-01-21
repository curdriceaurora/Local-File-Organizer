"""
Naming Analyzer - Advanced Filename Analysis

This module provides advanced analysis of filename patterns, including
semantic analysis, structure comparison, and pattern matching utilities.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
import re
from collections import Counter
from difflib import SequenceMatcher


@dataclass
class NameStructure:
    """Analyzed structure of a filename."""
    original: str
    tokens: List[str] = field(default_factory=list)
    delimiters: List[str] = field(default_factory=list)
    has_date: bool = False
    has_version: bool = False
    has_numbers: bool = False
    word_count: int = 0
    char_count: int = 0
    structure_hash: str = ""

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'original': self.original,
            'tokens': self.tokens,
            'delimiters': self.delimiters,
            'has_date': self.has_date,
            'has_version': self.has_version,
            'has_numbers': self.has_numbers,
            'word_count': self.word_count,
            'char_count': self.char_count,
            'structure_hash': self.structure_hash
        }


class NamingAnalyzer:
    """
    Advanced filename analyzer for pattern detection and comparison.

    Provides utilities for analyzing filename structures, comparing patterns,
    and identifying naming conventions.
    """

    # Version patterns
    VERSION_PATTERNS = [
        r'v\d+',
        r'V\d+',
        r'version[-_]?\d+',
        r'\d+\.\d+',
        r'\d+\.\d+\.\d+',
        r'_v?\d+$',
        r'_final',
        r'_draft',
        r'_rev\d+',
    ]

    # Common word separators
    SEPARATORS = ['_', '-', '.', ' ']

    def __init__(self):
        """Initialize the naming analyzer."""
        self._structure_cache: Dict[str, NameStructure] = {}

    def analyze_structure(self, filename: str) -> NameStructure:
        """
        Analyze the structure of a filename.

        Args:
            filename: Filename to analyze

        Returns:
            NameStructure object with analysis results
        """
        # Check cache
        if filename in self._structure_cache:
            return self._structure_cache[filename]

        name = Path(filename).stem

        structure = NameStructure(original=filename)

        # Tokenize
        structure.tokens = self._tokenize(name)
        structure.delimiters = self._extract_delimiters(name)

        # Detect features
        structure.has_date = self._has_date_pattern(name)
        structure.has_version = self._has_version_pattern(name)
        structure.has_numbers = bool(re.search(r'\d', name))

        # Count metrics
        structure.word_count = len(structure.tokens)
        structure.char_count = len(name)

        # Generate structure hash
        structure.structure_hash = self._generate_structure_hash(structure)

        # Cache result
        self._structure_cache[filename] = structure

        return structure

    def compare_structures(
        self,
        filename1: str,
        filename2: str
    ) -> Dict[str, any]:
        """
        Compare structures of two filenames.

        Args:
            filename1: First filename
            filename2: Second filename

        Returns:
            Dictionary with comparison results
        """
        struct1 = self.analyze_structure(filename1)
        struct2 = self.analyze_structure(filename2)

        # Token similarity
        token_similarity = self._calculate_token_similarity(
            struct1.tokens,
            struct2.tokens
        )

        # Delimiter similarity
        delim_sim = self._calculate_delimiter_similarity(
            struct1.delimiters,
            struct2.delimiters
        )

        # Structure similarity
        structure_sim = 1.0 if struct1.structure_hash == struct2.structure_hash else 0.0

        # Overall similarity (weighted average)
        overall_sim = (
            token_similarity * 0.5 +
            delim_sim * 0.3 +
            structure_sim * 0.2
        )

        return {
            'overall_similarity': overall_sim,
            'token_similarity': token_similarity,
            'delimiter_similarity': delim_sim,
            'structure_similarity': structure_sim,
            'same_structure': struct1.structure_hash == struct2.structure_hash,
            'compatible': overall_sim > 0.6
        }

    def find_common_pattern(self, filenames: List[str]) -> Optional[Dict[str, any]]:
        """
        Find common pattern across multiple filenames.

        Args:
            filenames: List of filenames to analyze

        Returns:
            Dictionary describing the common pattern or None
        """
        if not filenames:
            return None

        structures = [self.analyze_structure(f) for f in filenames]

        # Find common delimiters
        delimiter_sets = [set(s.delimiters) for s in structures]
        common_delimiters = set.intersection(*delimiter_sets) if delimiter_sets else set()

        # Find common tokens
        token_sets = [set(s.tokens) for s in structures]
        common_tokens = set.intersection(*token_sets) if token_sets else set()

        # Find common features
        has_date_count = sum(1 for s in structures if s.has_date)
        has_version_count = sum(1 for s in structures if s.has_version)

        pattern = {
            'sample_size': len(filenames),
            'common_delimiters': list(common_delimiters),
            'common_tokens': list(common_tokens),
            'date_frequency': has_date_count / len(filenames),
            'version_frequency': has_version_count / len(filenames),
            'avg_word_count': sum(s.word_count for s in structures) / len(structures),
            'avg_char_count': sum(s.char_count for s in structures) / len(structures),
        }

        # Determine pattern consistency
        structure_hashes = [s.structure_hash for s in structures]
        hash_counts = Counter(structure_hashes)
        most_common_hash, count = hash_counts.most_common(1)[0]

        pattern['consistency'] = count / len(filenames)
        pattern['dominant_structure'] = most_common_hash

        return pattern

    def extract_pattern_differences(
        self,
        original: str,
        corrected: str
    ) -> Dict[str, any]:
        """
        Extract differences between original and corrected filenames.

        Args:
            original: Original filename
            corrected: Corrected filename

        Returns:
            Dictionary describing the differences
        """
        struct_orig = self.analyze_structure(original)
        struct_corr = self.analyze_structure(corrected)

        differences = {
            'delimiter_change': struct_orig.delimiters != struct_corr.delimiters,
            'token_change': struct_orig.tokens != struct_corr.tokens,
            'structure_change': struct_orig.structure_hash != struct_corr.structure_hash,
            'added_date': not struct_orig.has_date and struct_corr.has_date,
            'removed_date': struct_orig.has_date and not struct_corr.has_date,
            'added_version': not struct_orig.has_version and struct_corr.has_version,
            'removed_version': struct_orig.has_version and not struct_corr.has_version,
        }

        # Token differences
        orig_tokens = set(struct_orig.tokens)
        corr_tokens = set(struct_corr.tokens)

        differences['added_tokens'] = list(corr_tokens - orig_tokens)
        differences['removed_tokens'] = list(orig_tokens - corr_tokens)
        differences['common_tokens'] = list(orig_tokens.intersection(corr_tokens))

        # Delimiter differences
        if differences['delimiter_change']:
            differences['old_delimiters'] = struct_orig.delimiters
            differences['new_delimiters'] = struct_corr.delimiters

        # Calculate edit distance
        differences['edit_distance'] = self._calculate_edit_distance(
            original,
            corrected
        )

        return differences

    def identify_naming_style(self, filename: str) -> str:
        """
        Identify the naming style used in a filename.

        Args:
            filename: Filename to analyze

        Returns:
            Style identifier: 'snake_case', 'kebab-case', 'camelCase', 'PascalCase', 'mixed'
        """
        name = Path(filename).stem

        if '_' in name and name.islower():
            return 'snake_case'
        elif '-' in name and name.islower():
            return 'kebab-case'
        elif re.match(r'^[a-z]+([A-Z][a-z]*)+$', name):
            return 'camelCase'
        elif re.match(r'^[A-Z][a-z]+([A-Z][a-z]*)*$', name):
            return 'PascalCase'
        elif ' ' in name:
            return 'space_separated'
        else:
            return 'mixed'

    def normalize_filename(
        self,
        filename: str,
        target_style: str = 'snake_case'
    ) -> str:
        """
        Normalize filename to a specific naming style.

        Args:
            filename: Filename to normalize
            target_style: Target naming style

        Returns:
            Normalized filename
        """
        path = Path(filename)
        name = path.stem
        extension = path.suffix

        # Tokenize
        tokens = self._tokenize(name)

        # Apply target style
        if target_style == 'snake_case':
            normalized = '_'.join(t.lower() for t in tokens)
        elif target_style == 'kebab-case':
            normalized = '-'.join(t.lower() for t in tokens)
        elif target_style == 'camelCase':
            normalized = tokens[0].lower() + ''.join(t.capitalize() for t in tokens[1:])
        elif target_style == 'PascalCase':
            normalized = ''.join(t.capitalize() for t in tokens)
        elif target_style == 'space_separated':
            normalized = ' '.join(t.lower() for t in tokens)
        else:
            normalized = name

        return normalized + extension

    def extract_semantic_components(self, filename: str) -> Dict[str, any]:
        """
        Extract semantic components from a filename.

        Args:
            filename: Filename to analyze

        Returns:
            Dictionary with semantic components
        """
        name = Path(filename).stem
        structure = self.analyze_structure(filename)

        components = {
            'base_name': name,
            'tokens': structure.tokens,
            'potential_description': [],
            'potential_metadata': []
        }

        # Identify metadata vs description tokens
        for token in structure.tokens:
            if self._is_metadata_token(token):
                components['potential_metadata'].append(token)
            else:
                components['potential_description'].append(token)

        # Extract version if present
        if structure.has_version:
            version_match = self._extract_version(name)
            if version_match:
                components['version'] = version_match

        # Extract date if present
        if structure.has_date:
            date_match = self._extract_date(name)
            if date_match:
                components['date'] = date_match

        return components

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text by separators and camelCase."""
        # First split by explicit separators
        pattern = '|'.join(re.escape(sep) for sep in self.SEPARATORS)
        if pattern:
            parts = re.split(pattern, text)
        else:
            parts = [text]

        # Then split camelCase
        tokens = []
        for part in parts:
            if not part:
                continue
            # Split on camelCase boundaries
            subparts = re.sub('([a-z])([A-Z])', r'\1 \2', part).split()
            tokens.extend(subparts)

        return [t for t in tokens if t]

    def _extract_delimiters(self, text: str) -> List[str]:
        """Extract delimiters from text."""
        delimiters = []
        for sep in self.SEPARATORS:
            if sep in text:
                delimiters.append(sep)
        return delimiters

    def _has_date_pattern(self, text: str) -> bool:
        """Check if text contains a date pattern."""
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',
            r'\d{4}_\d{2}_\d{2}',
            r'\d{2}-\d{2}-\d{4}',
            r'\d{8}',
        ]
        return any(re.search(pattern, text) for pattern in date_patterns)

    def _has_version_pattern(self, text: str) -> bool:
        """Check if text contains a version pattern."""
        return any(re.search(pattern, text) for pattern in self.VERSION_PATTERNS)

    def _generate_structure_hash(self, structure: NameStructure) -> str:
        """Generate a hash representing the structure."""
        import hashlib

        # Create structure signature
        signature = f"{len(structure.tokens)}:{','.join(structure.delimiters)}"
        signature += f":{structure.has_date}:{structure.has_version}"

        return hashlib.md5(signature.encode()).hexdigest()[:8]

    def _calculate_token_similarity(
        self,
        tokens1: List[str],
        tokens2: List[str]
    ) -> float:
        """Calculate similarity between token lists."""
        if not tokens1 or not tokens2:
            return 0.0

        set1 = set(t.lower() for t in tokens1)
        set2 = set(t.lower() for t in tokens2)

        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))

        return intersection / union if union > 0 else 0.0

    def _calculate_delimiter_similarity(
        self,
        delims1: List[str],
        delims2: List[str]
    ) -> float:
        """Calculate similarity between delimiter lists."""
        if not delims1 and not delims2:
            return 1.0

        if not delims1 or not delims2:
            return 0.0

        set1 = set(delims1)
        set2 = set(delims2)

        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))

        return intersection / union if union > 0 else 0.0

    def _calculate_edit_distance(self, str1: str, str2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(str1) < len(str2):
            return self._calculate_edit_distance(str2, str1)

        if len(str2) == 0:
            return len(str1)

        previous_row = range(len(str2) + 1)
        for i, c1 in enumerate(str1):
            current_row = [i + 1]
            for j, c2 in enumerate(str2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _is_metadata_token(self, token: str) -> bool:
        """Check if token is likely metadata (version, date, etc)."""
        return (
            self._has_version_pattern(token) or
            self._has_date_pattern(token) or
            token.lower() in ['final', 'draft', 'copy', 'backup', 'temp', 'old', 'new']
        )

    def _extract_version(self, text: str) -> Optional[str]:
        """Extract version string from text."""
        for pattern in self.VERSION_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None

    def _extract_date(self, text: str) -> Optional[str]:
        """Extract date string from text."""
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',
            r'\d{4}_\d{2}_\d{2}',
            r'\d{2}-\d{2}-\d{4}',
            r'\d{8}',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None
