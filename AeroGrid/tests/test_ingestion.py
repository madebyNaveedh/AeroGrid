"""Unit tests for the Knowledge Base Ingestion Script.

Validates environment discovery, missing PDF error handling, and parameter parsing.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from ingest_uae_policies import UAEPoliciesIngestor


class TestKBVectorizationIngestor(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_missing_directory_error_handling(self) -> None:
        missing_dir = os.path.join(self.temp_dir, "non_existent_subdir")
        ingestor = UAEPoliciesIngestor(pdf_dir=missing_dir)
        with self.assertRaises(FileNotFoundError) as ctx:
            ingestor.validate_environment()
        self.assertIn("did not exist", str(ctx.exception))
        self.assertTrue(os.path.exists(missing_dir), "Should create directory on missing")

    def test_empty_directory_error_handling(self) -> None:
        empty_dir = os.path.join(self.temp_dir, "empty_pdf_dir")
        os.makedirs(empty_dir, exist_ok=True)
        ingestor = UAEPoliciesIngestor(pdf_dir=empty_dir)
        with self.assertRaises(FileNotFoundError) as ctx:
            ingestor.validate_environment()
        self.assertIn("No PDF files found", str(ctx.exception))

    def test_valid_pdf_discovery(self) -> None:
        valid_dir = os.path.join(self.temp_dir, "valid_pdfs")
        os.makedirs(valid_dir, exist_ok=True)
        # Create a dummy PDF file
        dummy_pdf = os.path.join(valid_dir, "test_policy.pdf")
        with open(dummy_pdf, "wb") as f:
            f.write(b"%PDF-1.4 dummy pdf header and trailer %%EOF")

        ingestor = UAEPoliciesIngestor(pdf_dir=valid_dir)
        pdf_files = ingestor.validate_environment()
        self.assertEqual(len(pdf_files), 1)
        self.assertEqual(pdf_files[0].name, "test_policy.pdf")


if __name__ == "__main__":
    unittest.main()

