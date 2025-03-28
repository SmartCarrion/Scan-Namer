#!/usr/bin/env python3
# scan_agent.py - An agent that monitors a folder for newly scanned documents and renames them based on their content.

import os
import re
import time
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Set
import unicodedata
import argparse
import tempfile

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
try:
    from pdf2image import convert_from_path
    PDF_SUPPORT = True
except ImportError:
    logger.warning("pdf2image not installed. PDF support disabled.")
    PDF_SUPPORT = False

# Configure logging
# Force UTF-8 encoding for console output to handle special characters in filenames
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# File handler
file_handler = logging.FileHandler('scan_agent.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Default filename pattern for Microsoft Lens
# Format: "MM_DD_YY, HH_MM AM/PM Microsoft Lens.jpg"
# Note: Handles regular spaces and Unicode narrow non-breaking spaces (\u202f)
DEFAULT_FILENAME_PATTERN = re.compile(
    r"^\d{1,2}_\d{1,2}_\d{1,2},?\s+\d{1,2}_\d{2}[\s\u202f]*(?:AM|PM)[\s\u202f]*Microsoft Lens(?:\(\d+\))?\.(jpg|jpeg|png|pdf)$",
    re.IGNORECASE
)

# Log the pattern for debugging
logger.info(f"Using filename pattern: {DEFAULT_FILENAME_PATTERN.pattern}")


class ScanAgent:
    """Agent that monitors for new scans and renames them based on content analysis."""
    
    def __init__(self):
        """Initialize the scan agent with configuration from environment variables."""
        self._load_config()
        self._init_openai_client()
        self._processed_files: Set[str] = set()
        logger.info(f"ScanAgent initialized. Monitoring folder: {self.scan_folder}")

    def _load_config(self) -> None:
        """Load configuration from .env file."""
        if not load_dotenv():
            logger.warning("No .env file found. Using environment variables.")
        
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        scan_folder = os.getenv("SCAN_FOLDER_PATH")
        if not scan_folder:
            raise ValueError("SCAN_FOLDER_PATH environment variable is required")
        
        self.scan_folder = Path(scan_folder)
        if not self.scan_folder.exists() or not self.scan_folder.is_dir():
            raise ValueError(f"Scan folder does not exist or is not a directory: {self.scan_folder}")
        
        self.check_interval = int(os.getenv("CHECK_INTERVAL", "60"))
        self.continuous = os.getenv("CONTINUOUS_MONITORING", "False").lower() == "true"
        logger.debug(f"Config loaded: check_interval={self.check_interval}, continuous={self.continuous}")

    def _init_openai_client(self) -> None:
        """Initialize the OpenAI client."""
        self.openai_client = OpenAI(api_key=self.api_key)
        logger.debug("OpenAI client initialized")

    def find_unprocessed_files(self) -> List[Path]:
        """Find files in the scan folder that match the default pattern and haven't been processed."""
        files_to_process = []
        try:
            logger.info(f"Scanning directory: {self.scan_folder}")
            
            # Debug: List all files in the directory
            all_files = list(self.scan_folder.iterdir())
            if not all_files:
                logger.warning(f"Directory is empty: {self.scan_folder}")
            else:
                logger.info(f"Found {len(all_files)} total files/folders in directory")
                
                # If force_reprocess is enabled, log the files we've seen before
                if hasattr(self, '_force_reprocess') and self._force_reprocess:
                    logger.info(f"Previously processed files count: {len(self._processed_files)}")
            
            for item in self.scan_folder.iterdir():
                if not item.is_file():
                    continue  # Skip directories
                    
                # Log all files for debugging
                logger.info(f"Found file: {item.name}")
                
                # Normalize the filename to handle Unicode variations
                normalized_name = self._normalize_filename(item.name)
                
                # Debug: print the normalized name to see if it's different
                if normalized_name != item.name:
                    logger.info(f"Normalized name: {normalized_name}")
                
                # Check if it matches our pattern
                if not DEFAULT_FILENAME_PATTERN.match(normalized_name):
                    logger.info(f"File doesn't match pattern: {item.name}")
                    continue
                    
                # Check if we've processed it before
                if str(item) in self._processed_files:
                    logger.info(f"File was already processed: {item.name}")
                    continue
                    
                # If we got here, file is eligible for processing
                files_to_process.append(item)
                logger.info(f"Will process file: {item.name}")
                
        except Exception as e:
            logger.error(f"Error scanning directory {self.scan_folder}: {e}")
        
        return files_to_process

    def _normalize_filename(self, filename: str) -> str:
        """Normalize Unicode characters in the filename for consistent processing."""
        # This converts compatible Unicode characters to their canonical form
        # For example, it will convert various Unicode spaces to standard spaces
        return unicodedata.normalize('NFKC', filename)

    def process_scan(self, file_path: Path) -> None:
        """Process a single scanned document."""
        logger.info(f"Processing scan: {file_path.name}")
        
        # Mark as processed to avoid duplicate processing
        self._processed_files.add(str(file_path))
        
        # Skip if file no longer exists (may have been moved or deleted)
        if not file_path.exists():
            logger.warning(f"File no longer exists: {file_path}")
            return
        
        # Get suggested filename from OpenAI
        suggested_name = self._get_suggested_name(file_path)
        if not suggested_name:
            logger.warning(f"Could not get a valid filename suggestion for {file_path.name}")
            return
        
        # Rename the file
        self._rename_file(file_path, suggested_name)

    def _get_suggested_name(self, file_path: Path) -> Optional[str]:
        """Get a suggested filename from the OpenAI API based on the image content."""
        try:
            # Special handling for PDFs
            if file_path.suffix.lower() == '.pdf':
                if not PDF_SUPPORT:
                    logger.error("PDF processing requires pdf2image. Install with 'pip install pdf2image'")
                    logger.error("You'll also need to install poppler:")
                    logger.error("  Windows: https://github.com/oschwartz10612/poppler-windows/releases/")
                    logger.error("  Mac: brew install poppler")
                    logger.error("  Linux: apt-get install poppler-utils")
                    return None
                
                return self._get_suggested_name_for_pdf(file_path)
                
            # Handle regular images
            # Encode image to base64
            base64_image = self._encode_image(file_path)
            if not base64_image:
                return None
            
            # Determine mime type based on file extension
            file_extension = file_path.suffix.lower()
            mime_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
            }.get(file_extension, "application/octet-stream")
            
            # Call OpenAI with the image
            return self._get_suggestion_from_api(base64_image, mime_type)
            
        except Exception as e:
            logger.error(f"Error getting suggested name for {file_path.name}: {e}")
            return None

    def _get_suggested_name_for_pdf(self, pdf_path: Path) -> Optional[str]:
        """Process a PDF file by converting first page to image and sending to OpenAI."""
        try:
            logger.info(f"Converting first page of PDF to image: {pdf_path.name}")
            
            # Create a temporary directory to store the converted images
            with tempfile.TemporaryDirectory() as temp_dir:
                # Convert first page of PDF to image
                # dpi=200 is a good balance between quality and file size
                images = convert_from_path(pdf_path, dpi=200, first_page=1, last_page=1, output_folder=temp_dir)
                
                if not images:
                    logger.error(f"Failed to convert PDF to image: {pdf_path.name}")
                    return None
                    
                # Save the first page as a temporary JPG file
                first_page = images[0]
                temp_image_path = Path(temp_dir) / "temp_page.jpg"
                first_page.save(temp_image_path, "JPEG")
                
                # Encode the image
                with open(temp_image_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                
                # Get suggestion from API
                return self._get_suggestion_from_api(base64_image, "image/jpeg")
                
        except Exception as e:
            logger.error(f"Error processing PDF {pdf_path.name}: {e}")
            return None

    def _get_suggestion_from_api(self, base64_image: str, mime_type: str) -> Optional[str]:
        """Get filename suggestion from OpenAI API for the given image data."""
        # Prepare prompt for OpenAI
        prompt = (
            f"You are looking at a scanned document. Suggest a clear, concise filename based on its content. "
            f"The filename should be descriptive and include key information like document type, company names, "
            f"dates, or subject matter. Use underscores instead of spaces. "
            f"Do NOT include the file extension. "
            f"Respond with ONLY the suggested filename, no explanations or additional text."
        )
        
        try:
            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                },
                            },
                        ],
                    }
                ],
                max_tokens=50,
                temperature=0.3,
            )
            
            # Extract and sanitize the suggested name
            suggested_name = response.choices[0].message.content.strip()
            logger.info(f"OpenAI suggested name: {suggested_name}")
            
            return self._sanitize_filename(suggested_name)
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            return None

    def _encode_image(self, image_path: Path) -> Optional[str]:
        """Encode image to base64 for API transmission."""
        try:
            # For large files, resize image to reduce API costs and improve performance
            max_size_mb = 5
            if image_path.stat().st_size > (max_size_mb * 1024 * 1024) and image_path.suffix.lower() in ('.jpg', '.jpeg', '.png'):
                return self._resize_and_encode_image(image_path)
            
            # For smaller files or PDFs, encode directly
            with open(image_path, "rb") as file:
                return base64.b64encode(file.read()).decode('utf-8')
                
        except Exception as e:
            logger.error(f"Error encoding image {image_path.name}: {e}")
            return None

    def _resize_and_encode_image(self, image_path: Path) -> Optional[str]:
        """Resize image to a more manageable size and encode to base64."""
        try:
            with Image.open(image_path) as img:
                # Calculate new dimensions while maintaining aspect ratio
                max_dimension = 1600
                width, height = img.size
                if width > max_dimension or height > max_dimension:
                    if width > height:
                        new_width = max_dimension
                        new_height = int((height * max_dimension) / width)
                    else:
                        new_height = max_dimension
                        new_width = int((width * max_dimension) / height)
                    
                    # Resize image
                    img = img.resize((new_width, new_height), Image.LANCZOS)
                
                # Save to bytes and encode
                import io
                buffer = io.BytesIO()
                img.save(buffer, format=img.format)
                return base64.b64encode(buffer.getvalue()).decode('utf-8')
                
        except Exception as e:
            logger.error(f"Error resizing image {image_path.name}: {e}")
            return None

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize the filename to ensure it's valid for file systems."""
        # Replace invalid characters
        sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Replace spaces with underscores
        sanitized = re.sub(r'\s+', '_', sanitized)
        # Remove leading/trailing periods and spaces
        sanitized = sanitized.strip('. ')
        
        # If filename is empty after sanitization, use a default
        if not sanitized:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            sanitized = f"document_{timestamp}"
        
        # Limit length to avoid path issues
        if len(sanitized) > 100:
            sanitized = sanitized[:100]
            
        return sanitized

    def _rename_file(self, original_path: Path, new_basename: str) -> None:
        """Rename the file with the new base name, ensuring no conflicts."""
        file_extension = original_path.suffix
        new_filename = f"{new_basename}{file_extension}"
        new_path = original_path.with_name(new_filename)
        
        # If file already exists, append a number to avoid conflicts
        counter = 1
        while new_path.exists():
            new_filename = f"{new_basename}_{counter}{file_extension}"
            new_path = original_path.with_name(new_filename)
            counter += 1
            if counter > 100:  # Safety limit
                logger.error(f"Too many filename conflicts for {original_path.name}")
                return
        
        try:
            original_path.rename(new_path)
            logger.info(f"Renamed: {original_path.name} -> {new_path.name}")
        except Exception as e:
            logger.error(f"Error renaming {original_path.name}: {e}")

    def run_once(self, force_reprocess=False) -> None:
        """Process all matching files once.
        
        Args:
            force_reprocess: If True, reprocess all matching files, even if they've been processed before.
        """
        logger.info("Running one-time scan processing")
        
        # Store the force_reprocess flag for access in other methods
        self._force_reprocess = force_reprocess
        
        if force_reprocess:
            logger.info("Force reprocess flag is set - will reprocess all matching files")
            # Clear the processed files set to force reprocessing
            self._processed_files.clear()
        
        files = self.find_unprocessed_files()
        
        if not files:
            logger.info("No new files to process")
            return
            
        logger.info(f"Found {len(files)} file(s) to process")
        
        # Sort files by creation time to process oldest first
        files.sort(key=lambda f: f.stat().st_ctime)
        
        # Group files that might be pages of the same document
        file_groups = self._group_related_files(files)
        
        # Process each group of related files
        for group_id, group_files in file_groups.items():
            if len(group_files) > 1:
                # Multi-page document
                logger.info(f"Processing multi-page document with {len(group_files)} pages")
                self._process_multipage_document(group_files)
            else:
                # Single page document
                self.process_scan(group_files[0])
        
        logger.info("One-time processing complete")

    def _group_related_files(self, files: List[Path]) -> Dict[str, List[Path]]:
        """Group files that might be pages of the same document.
        
        Files are considered related if:
        1. They were created within a short time of each other (default 60 seconds)
        2. They have the same or similar date in the filename
        
        Returns:
            A dictionary mapping group IDs to lists of files in each group.
        """
        if not files:
            return {}
        
        # Time window for grouping files (seconds)
        time_window = 60
        
        # Group files by creation time proximity
        groups: Dict[str, List[Path]] = {}
        current_group_id = datetime.fromtimestamp(files[0].stat().st_ctime).strftime('%Y%m%d_%H%M%S')
        current_group_time = files[0].stat().st_ctime
        groups[current_group_id] = [files[0]]
        
        for file in files[1:]:
            file_ctime = file.stat().st_ctime
            
            # If this file was created within the time window of the current group
            if file_ctime - current_group_time <= time_window:
                groups[current_group_id].append(file)
            else:
                # Start a new group
                current_group_id = datetime.fromtimestamp(file_ctime).strftime('%Y%m%d_%H%M%S')
                current_group_time = file_ctime
                groups[current_group_id] = [file]
        
        # Sort files within each group by creation time
        for group_id in groups:
            groups[group_id].sort(key=lambda f: f.stat().st_ctime)
        
        return groups

    def _process_multipage_document(self, files: List[Path]) -> None:
        """Process multiple files as pages of the same document.
        
        Args:
            files: List of file paths to process, sorted by creation time.
        """
        if not files:
            return
        
        # Use the first file to get a base name suggestion
        first_file = files[0]
        logger.info(f"Getting base name from first file: {first_file.name}")
        
        # Mark all files as processed to avoid reprocessing
        for file in files:
            self._processed_files.add(str(file))
        
        # Get suggested base name from first file
        base_name = self._get_suggested_name(first_file)
        if not base_name:
            logger.warning("Could not get a valid filename suggestion for the document")
            return
        
        # Rename each file with page number suffix
        for i, file in enumerate(files, 1):
            if not file.exists():
                logger.warning(f"File no longer exists: {file}")
                continue
            
            # Add page number to base name
            file_basename = f"{base_name}_page_{i:02d}"
            self._rename_file(file, file_basename)

    def run_continuously(self) -> None:
        """Run as a continuous monitoring agent."""
        logger.info(f"Starting continuous monitoring (checking every {self.check_interval} seconds)")
        
        # First, process any existing files
        self.run_once()
        
        # Set up watchdog for file system monitoring
        event_handler = ScanFileHandler(self)
        observer = Observer()
        observer.schedule(event_handler, str(self.scan_folder), recursive=False)
        observer.start()
        
        try:
            # Check periodically for files that might have been missed by the observer
            while True:
                time.sleep(self.check_interval)
                # Only process truly new files during continuous monitoring
                self.run_once(force_reprocess=False)
        except KeyboardInterrupt:
            logger.info("Stopping monitoring due to keyboard interrupt")
            observer.stop()
        finally:
            observer.join()

    def run(self) -> None:
        """Run the agent based on configuration (continuous or one-time)."""
        if self.continuous:
            self.run_continuously()
        else:
            self.run_once()


class ScanFileHandler(FileSystemEventHandler):
    """File system event handler for the scan agent."""
    
    def __init__(self, agent: ScanAgent):
        self.agent = agent
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            normalized_name = self.agent._normalize_filename(file_path.name)
            if DEFAULT_FILENAME_PATTERN.match(normalized_name):
                logger.info(f"New scan detected: {file_path.name}")
                # Wait a moment for the file to be fully written
                time.sleep(2)
                self.agent.process_scan(file_path)


def main():
    """Main entry point for the scan agent."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Scan Namer Agent')
    parser.add_argument('--force', '-f', action='store_true', 
                      help='Force reprocessing of all matching files, even if they have been processed before')
    parser.add_argument('--continuous', '-c', action='store_true',
                      help='Run in continuous monitoring mode, overriding the setting in .env')
    parser.add_argument('--once', '-o', action='store_true',
                      help='Run once and exit, overriding the setting in .env')
    parser.add_argument('--diagnostic', '-d', action='store_true',
                      help='Run in diagnostic mode: only list files and check pattern matching without processing')
    args = parser.parse_args()
    
    try:
        agent = ScanAgent()
        
        # Handle diagnostic mode first
        if args.diagnostic:
            logger.info("=== DIAGNOSTIC MODE ===")
            logger.info("This will only list files and check pattern matching without processing them")
            
            # List all files in the directory
            try:
                logger.info(f"Scanning directory: {agent.scan_folder}")
                all_files = list(agent.scan_folder.iterdir())
                
                if not all_files:
                    logger.info(f"Directory is empty: {agent.scan_folder}")
                else:
                    logger.info(f"Found {len(all_files)} items in directory")
                    
                    for item in all_files:
                        if item.is_dir():
                            logger.info(f"  Directory: {item.name}")
                        else:
                            # For files, check if they match our pattern
                            normalized_name = agent._normalize_filename(item.name)
                            matches = DEFAULT_FILENAME_PATTERN.match(normalized_name) is not None
                            status = "MATCHES PATTERN" if matches else "does NOT match pattern"
                            logger.info(f"  File: {item.name} - {status}")
                            
                            if normalized_name != item.name:
                                logger.info(f"  Normalized: {normalized_name}")
            except Exception as e:
                logger.error(f"Error in diagnostic mode: {e}")
                
            logger.info("=== DIAGNOSTIC MODE COMPLETED ===")
            return
        
        # Regular operation mode
        # Override continuous mode setting if specified in command line
        if args.continuous:
            agent.continuous = True
        elif args.once:
            agent.continuous = False
        
        if agent.continuous:
            agent.run()
        else:
            # Run once with the force_reprocess flag if specified
            agent.run_once(force_reprocess=args.force)
            
    except KeyboardInterrupt:
        logger.info("Scan agent stopped by user")
    except Exception as e:
        logger.error(f"Scan agent error: {e}")


if __name__ == "__main__":
    main() 