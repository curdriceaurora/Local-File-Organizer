"""Tests for StorageReporter.

Covers reclamation calculation, text/JSON report generation, CSV/JSON export.
"""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from file_organizer.services.deduplication.reporter import StorageReporter


class TestStorageReporter(unittest.TestCase):
    """Test cases for StorageReporter."""

    def setUp(self):
        """Set up test fixtures."""
        self.reporter = StorageReporter()
        self.test_dir = Path(tempfile.mkdtemp())
        self.sample_groups = [
            {
                "count": 3,
                "total_size": 3000,
                "avg_similarity": 0.95,
                "representative": "/docs/report.pdf",
                "files": [
                    "/docs/report.pdf",
                    "/docs/report_copy.pdf",
                    "/docs/report_v2.pdf",
                ],
            },
            {
                "count": 2,
                "total_size": 2000,
                "avg_similarity": 0.88,
                "representative": "/images/photo.jpg",
                "files": ["/images/photo.jpg", "/images/photo_dup.jpg"],
            },
        ]
        self.sample_results = {
            "duplicate_groups": self.sample_groups,
            "total_documents": 10,
            "analyzed_documents": 8,
            "space_wasted": 3500,
            "num_groups": 2,
        }

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_init(self):
        """Test reporter initializes."""
        reporter = StorageReporter()
        self.assertIsNotNone(reporter)

    def test_calculate_reclamation(self):
        """Test storage reclamation calculation."""
        metrics = self.reporter.calculate_reclamation(self.sample_groups)

        self.assertEqual(metrics["total_duplicate_files"], 5)
        self.assertEqual(metrics["total_duplicate_groups"], 2)
        self.assertEqual(metrics["total_size"], 5000)
        self.assertIsInstance(metrics["recoverable_space"], int)
        self.assertGreater(metrics["recovery_percentage"], 0)

    def test_calculate_reclamation_empty(self):
        """Test reclamation with no groups."""
        metrics = self.reporter.calculate_reclamation([])
        self.assertEqual(metrics["total_duplicate_files"], 0)
        self.assertEqual(metrics["total_duplicate_groups"], 0)
        self.assertEqual(metrics["total_size"], 0)
        self.assertEqual(metrics["recovery_percentage"], 0)

    def test_generate_report_text(self):
        """Test text report generation."""
        report = self.reporter.generate_report(self.sample_results, "text")

        self.assertIn("DOCUMENT DEDUPLICATION REPORT", report)
        self.assertIn("Total documents analyzed: 8", report)
        self.assertIn("Duplicate groups found: 2", report)
        self.assertIn("Group 1:", report)
        self.assertIn("Group 2:", report)
        self.assertIn("report.pdf", report)
        self.assertIn("photo.jpg", report)

    def test_generate_report_json(self):
        """Test JSON report generation."""
        report = self.reporter.generate_report(self.sample_results, "json")

        parsed = json.loads(report)
        self.assertEqual(parsed["num_groups"], 2)
        self.assertEqual(parsed["analyzed_documents"], 8)

    def test_generate_report_text_with_many_files(self):
        """Test text report truncates groups with > 5 files."""
        big_group = {
            "count": 7,
            "total_size": 7000,
            "avg_similarity": 0.90,
            "representative": "/a.txt",
            "files": [f"/file{i}.txt" for i in range(7)],
        }
        results = {
            "duplicate_groups": [big_group],
            "total_documents": 10,
            "analyzed_documents": 10,
            "space_wasted": 6000,
            "num_groups": 1,
        }
        report = self.reporter.generate_report(results, "text")
        self.assertIn("... and 2 more", report)

    def test_export_to_csv(self):
        """Test CSV export."""
        csv_path = self.test_dir / "report.csv"
        self.reporter.export_to_csv(self.sample_groups, csv_path)

        self.assertTrue(csv_path.exists())
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Header + 2 data rows
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][0], "Group ID")
        self.assertEqual(rows[1][0], "1")
        self.assertEqual(rows[2][0], "2")

    def test_export_to_csv_error(self):
        """Test CSV export with invalid path raises."""
        bad_path = Path("/nonexistent_dir/subdir/report.csv")
        with self.assertRaises(OSError):
            self.reporter.export_to_csv(self.sample_groups, bad_path)

    def test_export_to_json(self):
        """Test JSON file export."""
        json_path = self.test_dir / "report.json"
        self.reporter.export_to_json(self.sample_results, json_path)

        self.assertTrue(json_path.exists())
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["num_groups"], 2)

    def test_export_to_json_error(self):
        """Test JSON export with invalid path raises."""
        bad_path = Path("/nonexistent_dir/subdir/report.json")
        with self.assertRaises(OSError):
            self.reporter.export_to_json(self.sample_results, bad_path)


if __name__ == "__main__":
    unittest.main()
