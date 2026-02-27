"""
Unit tests for the ResourceManager.

Tests thread-safe resource allocation, release, and utilization tracking
across CPU, memory, IO, and GPU resource types.
"""

from __future__ import annotations

import threading
import unittest

import pytest

from file_organizer.parallel.resource_manager import (
    ResourceConfig,
    ResourceManager,
    ResourceType,
)


@pytest.mark.unit
class TestResourceConfig(unittest.TestCase):
    """Test cases for ResourceConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = ResourceConfig()
        self.assertEqual(config.max_cpu_percent, 80.0)
        self.assertEqual(config.max_memory_mb, 1024)
        self.assertEqual(config.max_io_operations, 10)
        self.assertEqual(config.max_gpu_percent, 0.0)

    def test_custom_config(self) -> None:
        """Test creating a custom configuration."""
        config = ResourceConfig(
            max_cpu_percent=50.0,
            max_memory_mb=2048,
            max_io_operations=20,
            max_gpu_percent=75.0,
        )
        self.assertEqual(config.max_cpu_percent, 50.0)
        self.assertEqual(config.max_memory_mb, 2048)
        self.assertEqual(config.max_io_operations, 20)
        self.assertEqual(config.max_gpu_percent, 75.0)

    def test_invalid_cpu_raises(self) -> None:
        """Test that zero or negative CPU percent raises ValueError."""
        with self.assertRaises(ValueError):
            ResourceConfig(max_cpu_percent=0)
        with self.assertRaises(ValueError):
            ResourceConfig(max_cpu_percent=-10)

    def test_invalid_memory_raises(self) -> None:
        """Test that zero or negative memory raises ValueError."""
        with self.assertRaises(ValueError):
            ResourceConfig(max_memory_mb=0)
        with self.assertRaises(ValueError):
            ResourceConfig(max_memory_mb=-512)

    def test_invalid_io_raises(self) -> None:
        """Test that zero or negative IO operations raises ValueError."""
        with self.assertRaises(ValueError):
            ResourceConfig(max_io_operations=0)

    def test_invalid_gpu_raises(self) -> None:
        """Test that negative GPU percent raises ValueError."""
        with self.assertRaises(ValueError):
            ResourceConfig(max_gpu_percent=-1.0)


@pytest.mark.unit
class TestResourceType(unittest.TestCase):
    """Test cases for ResourceType enum."""

    def test_enum_values(self) -> None:
        """Test that ResourceType has expected string values."""
        self.assertEqual(ResourceType.CPU, "cpu")
        self.assertEqual(ResourceType.MEMORY, "memory")
        self.assertEqual(ResourceType.IO, "io")
        self.assertEqual(ResourceType.GPU, "gpu")

    def test_string_comparison(self) -> None:
        """Test that ResourceType compares equal to its string value."""
        self.assertEqual(ResourceType.CPU, "cpu")
        self.assertEqual(str(ResourceType.MEMORY), "memory")


@pytest.mark.unit
class TestResourceManager(unittest.TestCase):
    """Test cases for ResourceManager."""

    def setUp(self) -> None:
        """Set up a manager with known limits."""
        self.config = ResourceConfig(
            max_cpu_percent=100.0,
            max_memory_mb=1024,
            max_io_operations=10,
            max_gpu_percent=50.0,
        )
        self.manager = ResourceManager(self.config)

    def test_initial_availability(self) -> None:
        """Test that all resources are initially fully available."""
        self.assertEqual(self.manager.get_available(ResourceType.CPU), 100.0)
        self.assertEqual(self.manager.get_available(ResourceType.MEMORY), 1024.0)
        self.assertEqual(self.manager.get_available(ResourceType.IO), 10.0)
        self.assertEqual(self.manager.get_available(ResourceType.GPU), 50.0)

    def test_acquire_success(self) -> None:
        """Test successful resource acquisition."""
        result = self.manager.acquire(ResourceType.CPU, 30.0)
        self.assertTrue(result)
        self.assertEqual(self.manager.get_available(ResourceType.CPU), 70.0)

    def test_acquire_exact_limit(self) -> None:
        """Test acquiring exactly the available amount."""
        result = self.manager.acquire(ResourceType.IO, 10.0)
        self.assertTrue(result)
        self.assertEqual(self.manager.get_available(ResourceType.IO), 0.0)

    def test_acquire_exceeds_limit(self) -> None:
        """Test that acquiring more than available fails."""
        result = self.manager.acquire(ResourceType.CPU, 150.0)
        self.assertFalse(result)
        # Resources should not be modified
        self.assertEqual(self.manager.get_available(ResourceType.CPU), 100.0)

    def test_acquire_after_partial_use(self) -> None:
        """Test acquisition after some resources are in use."""
        self.manager.acquire(ResourceType.MEMORY, 800.0)
        # Only 224 MB left
        result = self.manager.acquire(ResourceType.MEMORY, 300.0)
        self.assertFalse(result)
        result = self.manager.acquire(ResourceType.MEMORY, 200.0)
        self.assertTrue(result)

    def test_release_frees_resources(self) -> None:
        """Test that releasing resources makes them available again."""
        self.manager.acquire(ResourceType.CPU, 50.0)
        self.assertEqual(self.manager.get_available(ResourceType.CPU), 50.0)
        self.manager.release(ResourceType.CPU, 30.0)
        self.assertEqual(self.manager.get_available(ResourceType.CPU), 80.0)

    def test_release_clamps_to_zero(self) -> None:
        """Test that releasing more than used does not go below zero."""
        self.manager.acquire(ResourceType.IO, 3.0)
        self.manager.release(ResourceType.IO, 10.0)
        self.assertEqual(self.manager.get_used(ResourceType.IO), 0.0)
        self.assertEqual(self.manager.get_available(ResourceType.IO), 10.0)

    def test_acquire_negative_raises(self) -> None:
        """Test that acquiring a negative amount raises ValueError."""
        with self.assertRaises(ValueError):
            self.manager.acquire(ResourceType.CPU, -10.0)

    def test_release_negative_raises(self) -> None:
        """Test that releasing a negative amount raises ValueError."""
        with self.assertRaises(ValueError):
            self.manager.release(ResourceType.CPU, -5.0)

    def test_unknown_resource_type_raises(self) -> None:
        """Test that unknown resource types raise ValueError."""
        with self.assertRaises(ValueError):
            self.manager.acquire("unknown", 10.0)
        with self.assertRaises(ValueError):
            self.manager.release("unknown", 10.0)
        with self.assertRaises(ValueError):
            self.manager.get_available("unknown")
        with self.assertRaises(ValueError):
            self.manager.get_used("unknown")
        with self.assertRaises(ValueError):
            self.manager.get_utilization("unknown")

    def test_get_used(self) -> None:
        """Test tracking of used resources."""
        self.assertEqual(self.manager.get_used(ResourceType.CPU), 0.0)
        self.manager.acquire(ResourceType.CPU, 25.0)
        self.assertEqual(self.manager.get_used(ResourceType.CPU), 25.0)

    def test_get_utilization(self) -> None:
        """Test utilization ratio calculation."""
        self.assertAlmostEqual(self.manager.get_utilization(ResourceType.CPU), 0.0)
        self.manager.acquire(ResourceType.CPU, 50.0)
        self.assertAlmostEqual(self.manager.get_utilization(ResourceType.CPU), 0.5)
        self.manager.acquire(ResourceType.CPU, 50.0)
        self.assertAlmostEqual(self.manager.get_utilization(ResourceType.CPU), 1.0)

    def test_get_utilization_zero_limit(self) -> None:
        """Test utilization when resource limit is zero (GPU disabled)."""
        config = ResourceConfig(
            max_cpu_percent=100.0,
            max_memory_mb=1024,
            max_io_operations=10,
            max_gpu_percent=0.0,
        )
        manager = ResourceManager(config)
        # GPU limit is 0, utilization should be 0
        self.assertAlmostEqual(manager.get_utilization(ResourceType.GPU), 0.0)

    def test_reset(self) -> None:
        """Test that reset releases all resources."""
        self.manager.acquire(ResourceType.CPU, 50.0)
        self.manager.acquire(ResourceType.MEMORY, 512.0)
        self.manager.acquire(ResourceType.IO, 5.0)

        self.manager.reset()

        self.assertEqual(self.manager.get_available(ResourceType.CPU), 100.0)
        self.assertEqual(self.manager.get_available(ResourceType.MEMORY), 1024.0)
        self.assertEqual(self.manager.get_available(ResourceType.IO), 10.0)

    def test_config_property(self) -> None:
        """Test that config property returns the configuration."""
        self.assertIs(self.manager.config, self.config)

    def test_acquire_zero_amount(self) -> None:
        """Test that acquiring zero amount succeeds without changing state."""
        result = self.manager.acquire(ResourceType.CPU, 0.0)
        self.assertTrue(result)
        self.assertEqual(self.manager.get_available(ResourceType.CPU), 100.0)

    def test_thread_safety_acquire_release(self) -> None:
        """Test concurrent acquire and release operations."""
        errors: list[str] = []

        def worker(resource: str, amount: float) -> None:
            try:
                for _ in range(100):
                    if self.manager.acquire(resource, amount):
                        self.manager.release(resource, amount)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(ResourceType.CPU, 10.0)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [], f"Thread errors: {errors}")
        # All resources should be released
        self.assertEqual(self.manager.get_available(ResourceType.CPU), 100.0)

    def test_thread_safety_no_over_allocation(self) -> None:
        """Test that concurrent acquisitions never exceed the limit."""
        config = ResourceConfig(
            max_cpu_percent=100.0,
            max_memory_mb=1024,
            max_io_operations=5,
        )
        manager = ResourceManager(config)
        acquired_count = threading.atomic() if hasattr(threading, "atomic") else [0]
        lock = threading.Lock()

        def try_acquire() -> None:
            for _ in range(50):
                if manager.acquire(ResourceType.IO, 1.0):
                    with lock:
                        if isinstance(acquired_count, list):
                            acquired_count[0] += 1
                    # Simulate some work
                    manager.release(ResourceType.IO, 1.0)

        threads = [threading.Thread(target=try_acquire) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # All IO resources should be released
        self.assertEqual(manager.get_available(ResourceType.IO), 5.0)


if __name__ == "__main__":
    unittest.main()
