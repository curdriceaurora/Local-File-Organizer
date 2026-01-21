"""Image quality assessment for selecting best version among duplicates.

This module provides quality scoring and comparison logic to automatically
select the highest quality image from a group of similar/duplicate images.
"""

from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import IntEnum
import logging

logger = logging.getLogger(__name__)


class ImageFormat(IntEnum):
    """Image format quality ranking (higher = better quality retention)."""

    UNKNOWN = 0
    GIF = 1      # Limited color palette, lossy
    BMP = 2      # Uncompressed but no metadata
    JPEG = 3     # Lossy compression
    WEBP = 4     # Modern format, good compression
    PNG = 5      # Lossless compression
    TIFF = 6     # Highest quality, uncompressed or lossless


@dataclass
class QualityMetrics:
    """Quality metrics for an image file."""

    resolution: int          # Width × Height (total pixels)
    width: int
    height: int
    file_size: int          # In bytes
    format: ImageFormat
    aspect_ratio: float
    is_compressed: bool
    has_transparency: bool
    color_depth: int        # Bits per pixel
    modification_time: float

    def to_dict(self) -> dict:
        """Convert metrics to dictionary."""
        return {
            'resolution': self.resolution,
            'width': self.width,
            'height': self.height,
            'file_size': self.file_size,
            'format': self.format.name,
            'aspect_ratio': self.aspect_ratio,
            'is_compressed': self.is_compressed,
            'has_transparency': self.has_transparency,
            'color_depth': self.color_depth,
            'modification_time': self.modification_time
        }


class ImageQualityAnalyzer:
    """Analyzes and compares image quality for duplicate detection."""

    # Format quality rankings
    FORMAT_RANKING = {
        '.tif': ImageFormat.TIFF,
        '.tiff': ImageFormat.TIFF,
        '.png': ImageFormat.PNG,
        '.webp': ImageFormat.WEBP,
        '.jpg': ImageFormat.JPEG,
        '.jpeg': ImageFormat.JPEG,
        '.bmp': ImageFormat.BMP,
        '.gif': ImageFormat.GIF,
    }

    # Weight factors for quality scoring (sum to 1.0)
    DEFAULT_WEIGHTS = {
        'resolution': 0.40,      # Most important: pixel count
        'format': 0.25,          # Format quality ranking
        'file_size': 0.20,       # Larger often means less compression
        'color_depth': 0.10,     # Bit depth matters
        'has_transparency': 0.05 # Transparency can be important
    }

    def __init__(self, weights: Optional[dict[str, float]] = None):
        """Initialize quality analyzer.

        Args:
            weights: Custom weights for quality factors (must sum to 1.0)
        """
        self.weights = weights or self.DEFAULT_WEIGHTS
        self._validate_weights()

        # Try to import PIL
        try:
            from PIL import Image
            self.Image = Image
            self._pil_available = True
        except ImportError:
            logger.warning("PIL not available, quality analysis will be limited")
            self.Image = None
            self._pil_available = False

    def _validate_weights(self) -> None:
        """Validate that weights sum to approximately 1.0."""
        total = sum(self.weights.values())
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"Weights must sum to 1.0, got {total}")

    def _get_format_from_extension(self, path: Path) -> ImageFormat:
        """Determine image format from file extension.

        Args:
            path: Path to image file

        Returns:
            ImageFormat enum value
        """
        ext = path.suffix.lower()
        return self.FORMAT_RANKING.get(ext, ImageFormat.UNKNOWN)

    def _extract_metrics_with_pil(self, path: Path) -> Optional[QualityMetrics]:
        """Extract detailed metrics using PIL.

        Args:
            path: Path to image file

        Returns:
            QualityMetrics object or None if extraction fails
        """
        if not self._pil_available:
            return None

        try:
            with self.Image.open(path) as img:
                width, height = img.size
                resolution = width * height

                # Determine compression
                is_compressed = img.format in ('JPEG', 'GIF', 'WEBP')

                # Check for transparency
                has_transparency = (
                    img.mode in ('RGBA', 'LA', 'PA') or
                    (img.mode == 'P' and 'transparency' in img.info)
                )

                # Calculate color depth
                mode_bits = {
                    '1': 1,        # 1-bit pixels, black and white
                    'L': 8,        # 8-bit pixels, grayscale
                    'P': 8,        # 8-bit pixels, palette
                    'RGB': 24,     # 3x8-bit pixels, true color
                    'RGBA': 32,    # 4x8-bit pixels, true color with alpha
                    'CMYK': 32,    # 4x8-bit pixels, color separation
                    'YCbCr': 24,   # 3x8-bit pixels, color video format
                    'LAB': 24,     # 3x8-bit pixels, L*a*b color space
                    'HSV': 24,     # 3x8-bit pixels, Hue, Saturation, Value
                    'I': 32,       # 32-bit signed integer pixels
                    'F': 32        # 32-bit floating point pixels
                }
                color_depth = mode_bits.get(img.mode, 24)

                file_size = path.stat().st_size
                format_enum = self._get_format_from_extension(path)
                aspect_ratio = width / height if height > 0 else 0
                modification_time = path.stat().st_mtime

                return QualityMetrics(
                    resolution=resolution,
                    width=width,
                    height=height,
                    file_size=file_size,
                    format=format_enum,
                    aspect_ratio=aspect_ratio,
                    is_compressed=is_compressed,
                    has_transparency=has_transparency,
                    color_depth=color_depth,
                    modification_time=modification_time
                )
        except Exception as e:
            logger.warning(f"Failed to extract metrics from {path}: {e}")
            return None

    def _extract_metrics_basic(self, path: Path) -> QualityMetrics:
        """Extract basic metrics without PIL (fallback).

        Args:
            path: Path to image file

        Returns:
            QualityMetrics with basic information
        """
        file_size = path.stat().st_size
        format_enum = self._get_format_from_extension(path)
        modification_time = path.stat().st_mtime

        # Estimate resolution based on file size and format
        # These are very rough estimates
        if format_enum == ImageFormat.JPEG:
            estimated_pixels = file_size * 10  # Typical JPEG compression
        elif format_enum == ImageFormat.PNG:
            estimated_pixels = file_size * 3   # PNG is less compressed
        else:
            estimated_pixels = file_size * 5

        return QualityMetrics(
            resolution=estimated_pixels,
            width=0,  # Unknown
            height=0,  # Unknown
            file_size=file_size,
            format=format_enum,
            aspect_ratio=1.0,  # Assume square
            is_compressed=format_enum in (ImageFormat.JPEG, ImageFormat.GIF, ImageFormat.WEBP),
            has_transparency=format_enum in (ImageFormat.PNG, ImageFormat.GIF, ImageFormat.WEBP),
            color_depth=24,  # Assume RGB
            modification_time=modification_time
        )

    def get_quality_metrics(self, image_path: Path) -> Optional[QualityMetrics]:
        """Extract quality metrics from an image file.

        Args:
            image_path: Path to the image file

        Returns:
            QualityMetrics object or None if file doesn't exist
        """
        if not image_path.exists():
            logger.error(f"Image file not found: {image_path}")
            return None

        # Try PIL first for accurate metrics
        metrics = self._extract_metrics_with_pil(image_path)

        # Fall back to basic metrics if PIL fails
        if metrics is None:
            metrics = self._extract_metrics_basic(image_path)

        return metrics

    def assess_quality(self, image_path: Path) -> float:
        """Calculate overall quality score for an image.

        The score is normalized to 0.0-1.0 range, with higher being better.

        Args:
            image_path: Path to the image file

        Returns:
            Quality score (0.0-1.0), or 0.0 if assessment fails
        """
        metrics = self.get_quality_metrics(image_path)
        if metrics is None:
            return 0.0

        score = 0.0

        # Resolution score (normalize to typical range: 0-25M pixels)
        max_resolution = 25_000_000  # 5000x5000
        resolution_score = min(metrics.resolution / max_resolution, 1.0)
        score += resolution_score * self.weights['resolution']

        # Format score (normalize to max format value)
        max_format = max(f.value for f in ImageFormat)
        format_score = metrics.format.value / max_format
        score += format_score * self.weights['format']

        # File size score (normalize to typical range: 0-50MB)
        # Larger is generally better (less compression) up to a point
        max_file_size = 50_000_000  # 50MB
        file_size_score = min(metrics.file_size / max_file_size, 1.0)
        score += file_size_score * self.weights['file_size']

        # Color depth score (normalize to 32-bit)
        max_depth = 32
        depth_score = metrics.color_depth / max_depth
        score += depth_score * self.weights['color_depth']

        # Transparency bonus (if present, it's desirable)
        transparency_score = 1.0 if metrics.has_transparency else 0.0
        score += transparency_score * self.weights['has_transparency']

        return score

    def compare_quality(self, img1: Path, img2: Path) -> int:
        """Compare quality of two images.

        Args:
            img1: Path to first image
            img2: Path to second image

        Returns:
            -1 if img1 is better quality
             0 if they're equal quality
             1 if img2 is better quality
        """
        score1 = self.assess_quality(img1)
        score2 = self.assess_quality(img2)

        # Use a small epsilon for equality comparison
        epsilon = 0.001

        if abs(score1 - score2) < epsilon:
            return 0
        elif score1 > score2:
            return -1
        else:
            return 1

    def get_best_quality(self, images: list[Path]) -> Optional[Path]:
        """Select the best quality image from a list.

        Args:
            images: list of image paths to compare

        Returns:
            Path to the highest quality image, or None if list is empty
        """
        if not images:
            return None

        if len(images) == 1:
            return images[0]

        # Score all images
        scored_images = [
            (img, self.assess_quality(img))
            for img in images
        ]

        # Filter out failed assessments
        valid_images = [(img, score) for img, score in scored_images if score > 0]

        if not valid_images:
            # All assessments failed, return first image as fallback
            logger.warning("All quality assessments failed, returning first image")
            return images[0]

        # Sort by score (descending) and return the best
        valid_images.sort(key=lambda x: x[1], reverse=True)
        best_image, best_score = valid_images[0]

        logger.info(f"Best quality: {best_image.name} (score: {best_score:.3f})")
        return best_image

    def is_likely_cropped(self, original: Path, candidate: Path,
                          threshold: float = 0.8) -> bool:
        """Detect if candidate is likely a cropped version of original.

        Args:
            original: Path to potential original image
            candidate: Path to potential cropped version
            threshold: Aspect ratio similarity threshold (0.0-1.0)

        Returns:
            True if candidate appears to be cropped from original
        """
        metrics1 = self.get_quality_metrics(original)
        metrics2 = self.get_quality_metrics(candidate)

        if not metrics1 or not metrics2:
            return False

        # Cropped image should have smaller resolution
        if metrics2.resolution >= metrics1.resolution:
            return False

        # Aspect ratios should be different (unless perfect crop)
        aspect_diff = abs(metrics1.aspect_ratio - metrics2.aspect_ratio)

        # If aspect ratios are very different, likely cropped
        if aspect_diff > 0.2:
            return True

        # Check if resolution difference is significant but not proportional
        # (proportional would indicate resize, not crop)
        ratio = metrics2.resolution / metrics1.resolution

        # If resolution is reduced but aspect ratio is similar, might be resize
        if ratio > threshold and aspect_diff < 0.1:
            return False

        # Smaller resolution with moderate aspect change suggests crop
        if ratio < threshold and aspect_diff > 0.05:
            return True

        return False

    def get_ranked_images(self, images: list[Path]) -> list[tuple[Path, float, QualityMetrics]]:
        """Get images ranked by quality with full details.

        Args:
            images: list of image paths to rank

        Returns:
            List of tuples (path, score, metrics) sorted by quality (best first)
        """
        results = []

        for img in images:
            metrics = self.get_quality_metrics(img)
            if metrics:
                score = self.assess_quality(img)
                results.append((img, score, metrics))

        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)

        return results
