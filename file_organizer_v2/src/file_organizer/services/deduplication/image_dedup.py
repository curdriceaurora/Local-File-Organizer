"""
Image deduplication module using perceptual hashing.

Provides ImageDeduplicator class with support for pHash, dHash, and aHash
algorithms for detecting visually similar images. Uses the imagededup library
for efficient perceptual hashing and Hamming distance calculations.
"""

import logging
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional, Set, Tuple

from imagededup.methods import AHash, DHash, PHash
from PIL import Image

logger = logging.getLogger(__name__)

# Supported hash algorithms
HashMethod = Literal["phash", "dhash", "ahash"]

# Supported image formats
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}


class ImageDeduplicator:
    """
    Detects duplicate and visually similar images using perceptual hashing.

    Uses imagededup library for computing perceptual hashes and comparing
    images based on visual similarity rather than exact byte matches.

    Supported algorithms:
    - pHash (Perceptual Hash): Best for general similarity detection
    - dHash (Difference Hash): Fast, good for detecting resized images
    - aHash (Average Hash): Fastest, good for exact duplicates

    Attributes:
        hash_method: Hash algorithm to use
        threshold: Maximum Hamming distance for similarity (0-64)
        hasher: Initialized hash computation object
    """

    def __init__(
        self,
        hash_method: HashMethod = "phash",
        threshold: int = 10
    ):
        """
        Initialize the ImageDeduplicator.

        Args:
            hash_method: Hash algorithm ("phash", "dhash", or "ahash")
            threshold: Maximum Hamming distance for images to be considered
                      similar. Lower values = more strict matching.
                      - 0: Exact match only
                      - 1-5: Very similar (minor compression/edits)
                      - 6-10: Similar (resized, color adjusted)
                      - 11-20: Somewhat similar (cropped, filtered)
                      - 21+: Potentially different images

        Raises:
            ValueError: If hash_method is not supported or threshold is invalid
        """
        if hash_method not in ("phash", "dhash", "ahash"):
            raise ValueError(
                f"Unsupported hash method: {hash_method}. "
                f"Use 'phash', 'dhash', or 'ahash'."
            )

        if not 0 <= threshold <= 64:
            raise ValueError(
                f"Threshold must be between 0 and 64, got {threshold}"
            )

        self.hash_method = hash_method
        self.threshold = threshold

        # Initialize hasher based on method
        if hash_method == "phash":
            self.hasher = PHash()
        elif hash_method == "dhash":
            self.hasher = DHash()
        else:  # ahash
            self.hasher = AHash()

    def get_image_hash(self, image_path: Path) -> Optional[str]:
        """
        Compute perceptual hash for a single image.

        Args:
            image_path: Path to image file

        Returns:
            Hexadecimal string representation of perceptual hash,
            or None if image could not be processed
        """
        if not image_path.exists():
            logger.warning(f"Image not found: {image_path}")
            return None

        if not image_path.is_file():
            logger.warning(f"Path is not a file: {image_path}")
            return None

        if image_path.suffix.lower() not in SUPPORTED_FORMATS:
            logger.warning(
                f"Unsupported image format: {image_path.suffix}. "
                f"Supported: {SUPPORTED_FORMATS}"
            )
            return None

        try:
            # imagededup expects string path
            encoding = self.hasher.encode_image(str(image_path))
            return encoding
        except (IOError, OSError) as e:
            logger.warning(f"Could not read image {image_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing image {image_path}: {e}")
            return None

    def compute_hamming_distance(self, hash1: str, hash2: str) -> int:
        """
        Calculate Hamming distance between two perceptual hashes.

        Hamming distance is the number of bit positions where the two
        hashes differ. Lower distance = more similar images.

        Args:
            hash1: First perceptual hash (hex string)
            hash2: Second perceptual hash (hex string)

        Returns:
            Hamming distance (0-64 for 64-bit hashes)

        Raises:
            ValueError: If hashes are not valid hex strings
        """
        try:
            # Convert hex strings to integers
            int1 = int(hash1, 16)
            int2 = int(hash2, 16)

            # XOR gives 1 for different bits, 0 for same bits
            xor = int1 ^ int2

            # Count number of 1s (different bits)
            distance = bin(xor).count('1')

            return distance
        except ValueError as e:
            raise ValueError(f"Invalid hash format: {e}") from e

    def compute_similarity(self, img1: Path, img2: Path) -> Optional[float]:
        """
        Compute similarity score between two images.

        Args:
            img1: Path to first image
            img2: Path to second image

        Returns:
            Similarity score from 0.0 (completely different) to 1.0 (identical),
            or None if either image could not be processed.
            Formula: 1 - (hamming_distance / 64)
        """
        hash1 = self.get_image_hash(img1)
        hash2 = self.get_image_hash(img2)

        if hash1 is None or hash2 is None:
            return None

        distance = self.compute_hamming_distance(hash1, hash2)

        # Convert distance to similarity score (0-1)
        # 64 is max possible distance for 64-bit hash
        similarity = 1.0 - (distance / 64.0)

        return similarity

    def find_duplicates(
        self,
        directory: Path,
        recursive: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, List[Path]]:
        """
        Find duplicate and similar images in a directory.

        Groups images by similarity, with each group containing one representative
        image and all its duplicates/similar images.

        Args:
            directory: Directory to scan for images
            recursive: If True, scan subdirectories recursively
            progress_callback: Optional callback function(current, total) called
                             during processing to report progress

        Returns:
            Dictionary mapping representative image hash to list of similar image paths.
            Only groups with 2+ images are included.
            Example:
            {
                "abc123...": [Path("img1.jpg"), Path("img2.jpg")],
                "def456...": [Path("img3.png"), Path("img4.png"), Path("img5.png")]
            }
        """
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        if not directory.is_dir():
            raise ValueError(f"Path is not a directory: {directory}")

        # Find all image files
        image_files = self._find_image_files(directory, recursive)

        if not image_files:
            logger.info(f"No images found in {directory}")
            return {}

        logger.info(f"Found {len(image_files)} images to process")

        # Compute hashes for all images
        image_hashes: Dict[Path, str] = {}

        for idx, img_path in enumerate(image_files, 1):
            img_hash = self.get_image_hash(img_path)
            if img_hash is not None:
                image_hashes[img_path] = img_hash

            if progress_callback:
                progress_callback(idx, len(image_files))

        logger.info(f"Successfully hashed {len(image_hashes)} images")

        # Find duplicates using imagededup's find_duplicates method
        # Create mapping from string path to hash for imagededup
        encoding_map = {str(path): hash_val for path, hash_val in image_hashes.items()}

        # imagededup's find_duplicates returns dict[filename] -> list of similar filenames
        duplicates_dict = self.hasher.find_duplicates(
            encoding_map=encoding_map,
            max_distance_threshold=self.threshold
        )

        # Convert back to Path objects and group by representative
        grouped_duplicates: Dict[str, List[Path]] = {}
        processed: Set[str] = set()

        for image_str, similar_list in duplicates_dict.items():
            if image_str in processed:
                continue

            # Only include if there are actual duplicates
            if similar_list:
                image_path = Path(image_str)
                similar_paths = [Path(s) for s in similar_list]

                # Use the hash as the key for grouping
                representative_hash = image_hashes[image_path]

                # Create group with all similar images
                group = [image_path] + similar_paths
                grouped_duplicates[representative_hash] = group

                # Mark all as processed
                processed.add(image_str)
                processed.update(similar_list)

        logger.info(f"Found {len(grouped_duplicates)} duplicate groups")

        return grouped_duplicates

    def cluster_by_similarity(
        self,
        images: List[Path],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[List[Path]]:
        """
        Cluster images into groups of similar images.

        Uses single-linkage clustering: if any image in a cluster is similar
        to a new image, the new image joins that cluster.

        Args:
            images: List of image paths to cluster
            progress_callback: Optional callback function(current, total) for progress

        Returns:
            List of clusters, where each cluster is a list of similar image paths
        """
        if not images:
            return []

        # Compute hashes for all images
        image_hashes: Dict[Path, str] = {}

        for idx, img_path in enumerate(images, 1):
            img_hash = self.get_image_hash(img_path)
            if img_hash is not None:
                image_hashes[img_path] = img_hash

            if progress_callback:
                progress_callback(idx, len(images))

        if not image_hashes:
            return []

        # Build clusters using single-linkage
        clusters: List[List[Path]] = []
        processed: Set[Path] = set()

        for img_path, img_hash in image_hashes.items():
            if img_path in processed:
                continue

            # Start new cluster
            cluster = [img_path]
            processed.add(img_path)

            # Find all similar images
            for other_path, other_hash in image_hashes.items():
                if other_path in processed:
                    continue

                distance = self.compute_hamming_distance(img_hash, other_hash)
                if distance <= self.threshold:
                    cluster.append(other_path)
                    processed.add(other_path)

            clusters.append(cluster)

        # Filter out single-image clusters
        clusters = [c for c in clusters if len(c) > 1]

        return clusters

    def batch_compute_hashes(
        self,
        image_paths: List[Path],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[Path, str]:
        """
        Compute perceptual hashes for multiple images.

        Processes images sequentially but returns all results together.
        Failed images are logged but don't stop batch processing.

        Args:
            image_paths: List of image paths to hash
            progress_callback: Optional callback function(current, total) for progress

        Returns:
            Dictionary mapping image paths to their perceptual hashes.
            Images that couldn't be hashed are excluded from results.
        """
        results: Dict[Path, str] = {}

        for idx, img_path in enumerate(image_paths, 1):
            img_hash = self.get_image_hash(img_path)
            if img_hash is not None:
                results[img_path] = img_hash

            if progress_callback:
                progress_callback(idx, len(image_paths))

        return results

    def _find_image_files(
        self,
        directory: Path,
        recursive: bool = True
    ) -> List[Path]:
        """
        Find all supported image files in a directory.

        Args:
            directory: Directory to search
            recursive: If True, search subdirectories

        Returns:
            List of paths to image files
        """
        image_files: List[Path] = []

        if recursive:
            pattern = "**/*"
        else:
            pattern = "*"

        for path in directory.glob(pattern):
            if path.is_file() and path.suffix.lower() in SUPPORTED_FORMATS:
                image_files.append(path)

        return image_files

    def validate_image(self, image_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate that an image can be processed.

        Checks:
        - File exists and is readable
        - Format is supported
        - Image can be opened with PIL

        Args:
            image_path: Path to image file

        Returns:
            Tuple of (is_valid, error_message)
            - If valid: (True, None)
            - If invalid: (False, "error description")
        """
        if not image_path.exists():
            return False, f"File not found: {image_path}"

        if not image_path.is_file():
            return False, f"Path is not a file: {image_path}"

        if image_path.suffix.lower() not in SUPPORTED_FORMATS:
            return False, f"Unsupported format: {image_path.suffix}"

        try:
            with Image.open(image_path) as img:
                # Try to load image data to verify it's not corrupt
                img.verify()
            return True, None
        except (IOError, OSError) as e:
            return False, f"Cannot read image: {e}"
        except Exception as e:
            return False, f"Corrupt or invalid image: {e}"
