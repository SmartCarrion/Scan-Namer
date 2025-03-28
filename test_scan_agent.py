#!/usr/bin/env python3
# test_scan_agent.py - Test script for the Scan Namer Agent

import os
import sys
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path to import scan_agent
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the scan_agent module after path setup
from scan_agent import ScanAgent, DEFAULT_FILENAME_PATTERN


class TestScanAgent(unittest.TestCase):
    """Test cases for the ScanAgent class."""

    def setUp(self):
        """Set up test environment before each test."""
        # Create a temporary directory
        self.temp_dir = tempfile.mkdtemp()
        
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            "OPENAI_API_KEY": "dummy_api_key",
            "SCAN_FOLDER_PATH": self.temp_dir,
            "CONTINUOUS_MONITORING": "False",
            "CHECK_INTERVAL": "10"
        })
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after each test."""
        # Remove temporary directory
        shutil.rmtree(self.temp_dir)
        # Stop patching environment variables
        self.env_patcher.stop()

    def test_load_config(self):
        """Test loading configuration from environment variables."""
        agent = ScanAgent()
        
        # Check if configuration was loaded correctly
        self.assertEqual(agent.api_key, "dummy_api_key")
        self.assertEqual(str(agent.scan_folder), self.temp_dir)
        self.assertEqual(agent.check_interval, 10)
        self.assertFalse(agent.continuous)

    def test_filename_pattern(self):
        """Test the default filename pattern regex."""
        # Valid filenames
        valid_names = [
            "3_28_22, 12_51 PM Microsoft Lens.jpg",
            "1_1_23, 9_05 AM Microsoft Lens.jpeg",
            "12_31_24, 11_59 PM Microsoft Lens.png",
            "5_15_21, 4_30 PM Microsoft Lens.pdf"
        ]
        
        # Invalid filenames
        invalid_names = [
            "document.jpg",
            "3_28_22 12_51 PM.jpg", # Missing comma
            "3-28-22, 12:51 PM Microsoft Lens.jpg", # Wrong separators
            "3_28_22, 12_51 PM Microsoft Scan.jpg", # Wrong app name
            "3_28_22, 12_51 PM Microsoft Lens.docx" # Unsupported extension
        ]
        
        # Test valid filenames
        for name in valid_names:
            self.assertTrue(DEFAULT_FILENAME_PATTERN.match(name), f"Should match: {name}")
        
        # Test invalid filenames
        for name in invalid_names:
            self.assertFalse(DEFAULT_FILENAME_PATTERN.match(name), f"Should not match: {name}")

    def test_find_unprocessed_files(self):
        """Test finding unprocessed files in the scan folder."""
        # Create test files
        test_files = [
            "3_28_22, 12_51 PM Microsoft Lens.jpg",
            "1_1_23, 9_05 AM Microsoft Lens.png",
            "document.pdf" # Should be ignored
        ]
        
        for filename in test_files:
            path = Path(self.temp_dir) / filename
            path.touch()
        
        # Initialize agent
        agent = ScanAgent()
        
        # Find unprocessed files
        unprocessed = agent.find_unprocessed_files()
        
        # Check if the right files were found
        self.assertEqual(len(unprocessed), 2)
        
        # Verify filenames
        filenames = [file.name for file in unprocessed]
        self.assertIn("3_28_22, 12_51 PM Microsoft Lens.jpg", filenames)
        self.assertIn("1_1_23, 9_05 AM Microsoft Lens.png", filenames)
        self.assertNotIn("document.pdf", filenames)

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        agent = ScanAgent()
        
        test_cases = [
            # (input, expected_output)
            ("Invoice #123", "Invoice_123"),
            ("File/with\\invalid:chars*?", "Filewithinvalidchars"),
            ("   Spaces   ", "Spaces"),
            ("Very " + "long" * 30 + " filename", "Very " + "long" * 16), # Truncated at 100 chars
            ("", "document_") # Empty string should get default name
        ]
        
        for input_name, expected in test_cases:
            sanitized = agent._sanitize_filename(input_name)
            # For the empty string case, just check it starts with "document_"
            if input_name == "":
                self.assertTrue(sanitized.startswith("document_"))
            else:
                self.assertEqual(sanitized, expected)

    @patch('openai.OpenAI')
    def test_rename_file(self, mock_openai):
        """Test renaming a file."""
        # Create test file
        test_filename = "3_28_22, 12_51 PM Microsoft Lens.jpg"
        test_file_path = Path(self.temp_dir) / test_filename
        test_file_path.touch()
        
        # Create agent with mocked OpenAI client
        agent = ScanAgent()
        
        # Rename file
        new_name = "Invoice_ABC_Company_2022-03-28"
        agent._rename_file(test_file_path, new_name)
        
        # Check if file was renamed
        new_file_path = Path(self.temp_dir) / f"{new_name}.jpg"
        self.assertTrue(new_file_path.exists())
        self.assertFalse(test_file_path.exists())
        
        # Test handling filename conflicts
        # Create another file with the target name
        conflict_file = Path(self.temp_dir) / "Invoice_XYZ_Company_2023-01-01.jpg"
        conflict_file.touch()
        
        # Create a file to rename
        another_test_file = Path(self.temp_dir) / "1_1_23, 9_05 AM Microsoft Lens.jpg"
        another_test_file.touch()
        
        # Rename to a name that already exists
        agent._rename_file(another_test_file, "Invoice_XYZ_Company_2023-01-01")
        
        # Check if file was renamed with a suffix
        renamed_with_suffix = Path(self.temp_dir) / "Invoice_XYZ_Company_2023-01-01_1.jpg"
        self.assertTrue(renamed_with_suffix.exists())
        self.assertFalse(another_test_file.exists())

    @patch.object(ScanAgent, '_get_suggested_name')
    def test_process_scan(self, mock_get_suggested_name):
        """Test processing a scan."""
        # Create test file
        test_filename = "3_28_22, 12_51 PM Microsoft Lens.jpg"
        test_file_path = Path(self.temp_dir) / test_filename
        test_file_path.touch()
        
        # Mock the suggested name
        mock_get_suggested_name.return_value = "Invoice_Test_Company_2022-03-28"
        
        # Create agent
        agent = ScanAgent()
        
        # Process the scan
        agent.process_scan(test_file_path)
        
        # Check if file was renamed
        renamed_file = Path(self.temp_dir) / "Invoice_Test_Company_2022-03-28.jpg"
        self.assertTrue(renamed_file.exists())
        self.assertFalse(test_file_path.exists())
        
        # Check if file was marked as processed
        self.assertIn(str(test_file_path), agent._processed_files)


if __name__ == "__main__":
    unittest.main() 