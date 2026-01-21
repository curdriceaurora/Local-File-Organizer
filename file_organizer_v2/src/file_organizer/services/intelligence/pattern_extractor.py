"""
Pattern Extraction Engine

This module implements pattern extraction from user corrections and file operations.
It analyzes naming patterns, identifies common structures, and generates reusable
pattern templates.

Features:
- Filename structure analysis and decomposition
- Common element extraction across multiple filenames
- Delimiter detection (underscore, hyphen, camelCase)
- Date format pattern recognition
- Prefix/suffix pattern identification
- Pattern normalization and standardization
- Structure similarity scoring
- Regex pattern generation from examples
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Pattern as RegexPattern
import re
from collections import Counter
from datetime import datetime


@dataclass
class PatternElement:
    """A single element of a naming pattern."""
    element_type: str  # 'delimiter', 'date', 'prefix', 'suffix', 'text', 'number'
    value: str
    position: int
    is_variable: bool = False
    pattern: Optional[str] = None  # Regex pattern if is_variable


@dataclass
class NamingPattern:
    """A structured naming pattern extracted from filenames."""
    pattern_id: str
    elements: List[PatternElement] = field(default_factory=list)
    delimiter: Optional[str] = None
    has_date: bool = False
    date_format: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    case_convention: str = "mixed"  # 'lower', 'upper', 'title', 'camel', 'mixed'
    example_files: List[str] = field(default_factory=list)
    confidence: float = 0.5

    def to_regex(self) -> str:
        """Convert pattern to regex string."""
        parts = []
        for elem in self.elements:
            if elem.is_variable and elem.pattern:
                parts.append(elem.pattern)
            else:
                # Escape special regex characters
                escaped = re.escape(elem.value)
                parts.append(escaped)
        return ''.join(parts)

    def to_template(self) -> str:
        """Convert pattern to human-readable template."""
        parts = []
        for elem in self.elements:
            if elem.is_variable:
                parts.append(f"{{{elem.element_type}}}")
            else:
                parts.append(elem.value)
        return ''.join(parts)


class NamingPatternExtractor:
    """
    Extracts naming patterns from filenames.

    This class analyzes filenames to identify structure, delimiters,
    date formats, and other patterns that can be learned and applied.
    """

    # Common date format patterns
    DATE_PATTERNS = [
        (r'\d{4}-\d{2}-\d{2}', 'YYYY-MM-DD'),
        (r'\d{4}_\d{2}_\d{2}', 'YYYY_MM_DD'),
        (r'\d{2}-\d{2}-\d{4}', 'DD-MM-YYYY'),
        (r'\d{2}_\d{2}_\d{4}', 'DD_MM_YYYY'),
        (r'\d{8}', 'YYYYMMDD'),
        (r'\d{4}\d{2}\d{2}', 'YYYYMMDD'),
        (r'\d{2}/\d{2}/\d{4}', 'DD/MM/YYYY'),
        (r'\d{4}/\d{2}/\d{2}', 'YYYY/MM/DD'),
    ]

    # Common delimiters
    DELIMITERS = ['_', '-', '.', ' ', '']

    def __init__(self):
        """Initialize the pattern extractor."""
        self._pattern_cache: Dict[str, NamingPattern] = {}

    def analyze_filename(self, filename: str) -> Dict[str, any]:
        """
        Analyze a single filename and extract its structure.

        Args:
            filename: Filename to analyze (without path)

        Returns:
            Dictionary with analyzed components
        """
        # Remove extension
        name_without_ext = Path(filename).stem

        analysis = {
            'original': filename,
            'name': name_without_ext,
            'extension': Path(filename).suffix.lower(),
            'delimiters': self.extract_delimiters(name_without_ext),
            'date_info': self.detect_date_format(name_without_ext),
            'has_numbers': bool(re.search(r'\d', name_without_ext)),
            'case_convention': self._detect_case_convention(name_without_ext),
            'length': len(name_without_ext),
            'word_count': len(re.findall(r'\w+', name_without_ext)),
        }

        # Extract potential prefix/suffix
        parts = self._split_by_delimiters(name_without_ext, analysis['delimiters'])
        if len(parts) > 0:
            analysis['potential_prefix'] = parts[0]
            analysis['potential_suffix'] = parts[-1] if len(parts) > 1 else None
            analysis['middle_parts'] = parts[1:-1] if len(parts) > 2 else []

        return analysis

    def extract_delimiters(self, filename: str) -> List[str]:
        """
        Extract delimiters used in a filename.

        Args:
            filename: Filename to analyze

        Returns:
            List of delimiters found (ordered by frequency)
        """
        delimiter_counts = Counter()

        for delimiter in self.DELIMITERS:
            if delimiter == '':
                continue
            count = filename.count(delimiter)
            if count > 0:
                delimiter_counts[delimiter] = count

        # Check for camelCase
        if re.search(r'[a-z][A-Z]', filename):
            delimiter_counts['camelCase'] = len(re.findall(r'[a-z][A-Z]', filename))

        return [delim for delim, _ in delimiter_counts.most_common()]

    def detect_date_format(self, filename: str) -> Optional[Dict[str, any]]:
        """
        Detect date format in filename.

        Args:
            filename: Filename to analyze

        Returns:
            Dictionary with date info or None if no date found
        """
        for pattern_str, format_name in self.DATE_PATTERNS:
            match = re.search(pattern_str, filename)
            if match:
                return {
                    'format': format_name,
                    'value': match.group(0),
                    'position': match.start(),
                    'pattern': pattern_str
                }
        return None

    def extract_common_elements(self, filenames: List[str]) -> List[str]:
        """
        Extract common elements across multiple filenames.

        Args:
            filenames: List of filenames to analyze

        Returns:
            List of common elements found in all files
        """
        if not filenames:
            return []

        # Analyze each filename
        all_parts = []
        for filename in filenames:
            name = Path(filename).stem
            delimiters = self.extract_delimiters(name)
            parts = self._split_by_delimiters(name, delimiters)
            all_parts.append(set(parts))

        # Find intersection
        if not all_parts:
            return []

        common = all_parts[0]
        for parts in all_parts[1:]:
            common = common.intersection(parts)

        return sorted(list(common))

    def identify_structure_pattern(self, filenames: List[str]) -> Optional[NamingPattern]:
        """
        Identify common structural pattern across filenames.

        Args:
            filenames: List of filenames to analyze

        Returns:
            NamingPattern object or None if no pattern found
        """
        if not filenames:
            return None

        # Analyze each file
        analyses = [self.analyze_filename(f) for f in filenames]

        # Find common delimiter
        delimiter_counts = Counter()
        for analysis in analyses:
            if analysis['delimiters']:
                delimiter_counts[analysis['delimiters'][0]] += 1

        common_delimiter = delimiter_counts.most_common(1)[0][0] if delimiter_counts else None

        # Find common date format
        date_format_counts = Counter()
        for analysis in analyses:
            if analysis['date_info']:
                date_format_counts[analysis['date_info']['format']] += 1

        common_date_format = date_format_counts.most_common(1)[0][0] if date_format_counts else None

        # Find common case convention
        case_counts = Counter(a['case_convention'] for a in analyses)
        common_case = case_counts.most_common(1)[0][0]

        # Build pattern
        pattern = NamingPattern(
            pattern_id=self._generate_pattern_id(filenames),
            delimiter=common_delimiter,
            has_date=common_date_format is not None,
            date_format=common_date_format,
            case_convention=common_case,
            example_files=filenames[:5],  # Keep first 5 as examples
            confidence=min(0.95, len(filenames) * 0.1)  # More files = higher confidence
        )

        # Identify common prefix/suffix
        prefixes = [a.get('potential_prefix', '') for a in analyses if a.get('potential_prefix')]
        suffixes = [a.get('potential_suffix', '') for a in analyses if a.get('potential_suffix')]

        if prefixes:
            prefix_counts = Counter(prefixes)
            if prefix_counts.most_common(1)[0][1] >= len(filenames) * 0.5:
                pattern.prefix = prefix_counts.most_common(1)[0][0]

        if suffixes:
            suffix_counts = Counter(suffixes)
            if suffix_counts.most_common(1)[0][1] >= len(filenames) * 0.5:
                pattern.suffix = suffix_counts.most_common(1)[0][0]

        # Build pattern elements
        self._build_pattern_elements(pattern, analyses)

        return pattern

    def suggest_naming_convention(self, file_info: Dict[str, any]) -> Optional[str]:
        """
        Suggest a naming convention based on file info.

        Args:
            file_info: Dictionary with file information

        Returns:
            Suggested filename or None
        """
        # This is a placeholder for suggesting naming conventions
        # based on learned patterns
        parts = []

        # Add prefix if available
        if file_info.get('prefix'):
            parts.append(file_info['prefix'])

        # Add main content
        if file_info.get('content'):
            parts.append(file_info['content'])

        # Add date if needed
        if file_info.get('include_date'):
            date_str = datetime.now().strftime('%Y-%m-%d')
            parts.append(date_str)

        # Add suffix if available
        if file_info.get('suffix'):
            parts.append(file_info['suffix'])

        if not parts:
            return None

        # Join with delimiter
        delimiter = file_info.get('delimiter', '_')
        filename = delimiter.join(parts)

        # Apply case convention
        case_convention = file_info.get('case_convention', 'lower')
        filename = self._apply_case_convention(filename, case_convention)

        # Add extension
        if file_info.get('extension'):
            filename += file_info['extension']

        return filename

    def calculate_similarity(self, filename1: str, filename2: str) -> float:
        """
        Calculate similarity score between two filenames.

        Args:
            filename1: First filename
            filename2: Second filename

        Returns:
            Similarity score between 0.0 and 1.0
        """
        analysis1 = self.analyze_filename(filename1)
        analysis2 = self.analyze_filename(filename2)

        similarity_factors = []

        # Delimiter similarity
        delim1 = set(analysis1['delimiters'])
        delim2 = set(analysis2['delimiters'])
        if delim1 or delim2:
            delim_sim = len(delim1.intersection(delim2)) / max(len(delim1), len(delim2))
            similarity_factors.append(delim_sim)

        # Date format similarity
        date1 = analysis1['date_info']
        date2 = analysis2['date_info']
        if date1 and date2:
            date_sim = 1.0 if date1['format'] == date2['format'] else 0.0
            similarity_factors.append(date_sim)
        elif not date1 and not date2:
            similarity_factors.append(1.0)
        else:
            similarity_factors.append(0.0)

        # Case convention similarity
        case_sim = 1.0 if analysis1['case_convention'] == analysis2['case_convention'] else 0.5
        similarity_factors.append(case_sim)

        # Extension similarity
        ext_sim = 1.0 if analysis1['extension'] == analysis2['extension'] else 0.0
        similarity_factors.append(ext_sim)

        # Calculate average
        return sum(similarity_factors) / len(similarity_factors) if similarity_factors else 0.0

    def generate_regex_pattern(self, filenames: List[str]) -> Optional[str]:
        """
        Generate a regex pattern that matches the given filenames.

        Args:
            filenames: List of example filenames

        Returns:
            Regex pattern string or None
        """
        pattern = self.identify_structure_pattern(filenames)
        if pattern:
            return pattern.to_regex()
        return None

    def _split_by_delimiters(self, text: str, delimiters: List[str]) -> List[str]:
        """Split text by multiple delimiters."""
        if not delimiters:
            return [text]

        # Create regex pattern for splitting
        pattern = '|'.join(re.escape(d) for d in delimiters if d != 'camelCase')

        if not pattern:
            return [text]

        parts = re.split(pattern, text)
        return [p for p in parts if p]  # Remove empty strings

    def _detect_case_convention(self, text: str) -> str:
        """Detect case convention used in text."""
        if text.islower():
            return 'lower'
        elif text.isupper():
            return 'upper'
        elif text.istitle():
            return 'title'
        elif re.match(r'^[a-z]+([A-Z][a-z]*)+$', text):
            return 'camel'
        elif re.match(r'^[A-Z][a-z]+([A-Z][a-z]*)*$', text):
            return 'pascal'
        else:
            return 'mixed'

    def _apply_case_convention(self, text: str, convention: str) -> str:
        """Apply case convention to text."""
        if convention == 'lower':
            return text.lower()
        elif convention == 'upper':
            return text.upper()
        elif convention == 'title':
            return text.title()
        elif convention == 'camel':
            words = re.split(r'[_\-\s]+', text)
            if not words:
                return text
            return words[0].lower() + ''.join(w.capitalize() for w in words[1:])
        elif convention == 'pascal':
            words = re.split(r'[_\-\s]+', text)
            return ''.join(w.capitalize() for w in words)
        else:
            return text

    def _generate_pattern_id(self, filenames: List[str]) -> str:
        """Generate unique pattern ID."""
        import hashlib
        content = ''.join(sorted(filenames[:5]))
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _build_pattern_elements(
        self,
        pattern: NamingPattern,
        analyses: List[Dict]
    ) -> None:
        """Build pattern elements from analyses."""
        # This is a simplified version - can be expanded
        position = 0

        if pattern.prefix:
            pattern.elements.append(PatternElement(
                element_type='prefix',
                value=pattern.prefix,
                position=position,
                is_variable=False
            ))
            position += 1

        if pattern.delimiter:
            pattern.elements.append(PatternElement(
                element_type='delimiter',
                value=pattern.delimiter,
                position=position,
                is_variable=False
            ))
            position += 1

        if pattern.has_date:
            pattern.elements.append(PatternElement(
                element_type='date',
                value='{date}',
                position=position,
                is_variable=True,
                pattern=r'\d{4}-\d{2}-\d{2}'  # Default date pattern
            ))
            position += 1

        if pattern.suffix:
            if pattern.delimiter:
                pattern.elements.append(PatternElement(
                    element_type='delimiter',
                    value=pattern.delimiter,
                    position=position,
                    is_variable=False
                ))
                position += 1

            pattern.elements.append(PatternElement(
                element_type='suffix',
                value=pattern.suffix,
                position=position,
                is_variable=False
            ))
