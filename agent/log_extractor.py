"""
Smart Log Extractor for Build Failures

Extracts relevant portions from potentially massive build logs.
"""
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SmartLogExtractor:
    """
    Extracts relevant error context from large build logs
    """

    # Error markers to search for
    ERROR_MARKERS = [
        "error:",
        "ERROR:",
        "FAILED:",
        "CMake Error",
        "undefined reference",
        "cannot find",
        "fatal error",
        "compilation terminated",
        "Error ",
        "FAIL ",
        "assertion failed",
        "Traceback",
    ]

    def __init__(self, max_excerpt_lines: int = 500):
        """
        Initialize log extractor

        Args:
            max_excerpt_lines: Maximum lines to extract
        """
        self.max_excerpt_lines = max_excerpt_lines

    def extract_relevant_error(self, log_path: str, platform: str = "unknown",
                              github_annotations: Dict = None) -> Dict:
        """
        Extract the most relevant error context from huge logs

        Args:
            log_path: Path to build log file
            platform: Platform identifier
            github_annotations: Optional GitHub annotations data to help classify error

        Returns:
            Dict with error excerpt and metadata
        """
        logger.info(f"Extracting error from log: {log_path}")

        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
            return self._create_error_context(
                content=f"ERROR: Could not read log file: {e}",
                context_type="error",
                error_type="log_read_error",
                metadata={"platform": platform}
            )

        total_lines = len(lines)
        logger.info(f"Log file has {total_lines} lines")

        # Find last error occurrence
        last_error_idx = self._find_last_error(lines)

        if last_error_idx is None:
            # No explicit error, grab last N lines
            logger.warning("No error marker found, using end of log")
            excerpt_lines = lines[-self.max_excerpt_lines:]
            context_type = "end_of_log"
            location = f"lines {max(0, total_lines - self.max_excerpt_lines)}-{total_lines}"
        else:
            # Extract context around error
            start = max(0, last_error_idx - 100)  # 100 lines before
            end = min(total_lines, last_error_idx + 400)  # 400 lines after
            excerpt_lines = lines[start:end]
            context_type = "error_context"
            location = f"lines {start}-{end} of {total_lines}"

        # Classify error type
        excerpt_text = "".join(excerpt_lines)
        error_type = self._classify_error(excerpt_text, github_annotations)

        logger.info(f"Extracted {len(excerpt_lines)} lines, error type: {error_type}")

        return self._create_error_context(
            content=excerpt_text,
            context_type=context_type,
            error_type=error_type,
            metadata={
                "platform": platform,
                "total_log_lines": total_lines,
                "excerpt_location": location,
                "excerpt_lines": len(excerpt_lines)
            }
        )

    def _find_last_error(self, lines: List[str]) -> Optional[int]:
        """
        Find index of last error marker in log

        Args:
            lines: Log file lines

        Returns:
            Index of last error, or None if not found
        """
        for i in range(len(lines) - 1, -1, -1):
            line_lower = lines[i].lower()
            if any(marker.lower() in line_lower for marker in self.ERROR_MARKERS):
                return i
        return None

    def _classify_error(self, excerpt: str, github_annotations: Dict = None) -> str:
        """
        Classify error type to help LLM understand context

        Args:
            excerpt: Error excerpt text
            github_annotations: Optional GitHub annotations to help classify

        Returns:
            Error classification string
        """
        text_lower = excerpt.lower()

        # First, check GitHub annotations if available (most reliable)
        if github_annotations and github_annotations.get('status') == 'success':
            job_name = github_annotations.get('job_name', '').lower()
            error_lines = github_annotations.get('error_annotations', [])

            # Check if it's a prep/check step failure
            if 'prep' in job_name or 'check' in job_name:
                # Look for exit code errors in prep phase
                if any('exit code' in line.lower() for line in error_lines):
                    return "prep_command_failure"

            # Check for specific error types in annotations
            annotation_text = ' '.join(error_lines).lower()
            if 'vcpkg' in annotation_text:
                return "vcpkg_dependency"
            elif 'cmake error' in annotation_text:
                return "cmake_configuration"
            elif 'undefined reference' in annotation_text or 'unresolved external' in annotation_text:
                return "linker_error"

        # Fall back to excerpt analysis
        # Order matters - check most specific first
        if "vcpkg" in text_lower or "triplet" in text_lower:
            return "vcpkg_dependency"
        elif "cmake error" in text_lower:  # More specific - require "cmake error" not just "cmake"
            return "cmake_configuration"
        elif "undefined reference" in text_lower or "unresolved external" in text_lower:
            return "linker_error"
        elif re.search(r'\.(cpp|cc|cxx|c|h|hpp):', excerpt):
            return "compilation_error"
        elif ("test" in text_lower or "pytest" in text_lower) and \
             ("failed" in text_lower or "assertion" in text_lower or "traceback" in text_lower):
            return "test_failure"
        elif "no module named" in text_lower or "importerror" in text_lower:
            return "python_import_error"
        elif "nameerror" in text_lower or "attributeerror" in text_lower:
            return "python_runtime_error"
        else:
            return "unknown"

    def _create_error_context(self, content: str, context_type: str,
                            error_type: str, metadata: Dict) -> Dict:
        """
        Package excerpt with metadata for LLM

        Args:
            content: Excerpt content
            context_type: Type of context
            error_type: Classified error type
            metadata: Additional metadata

        Returns:
            Context dict ready for LLM
        """
        return {
            "error_excerpt": content,
            "context_type": context_type,
            "error_type": error_type,
            "metadata_dict": metadata,  # Keep dict for programmatic access
            "metadata": self._format_metadata(metadata),  # Formatted string for prompt
            "excerpt_lines": len(content.splitlines())
        }

    def _format_metadata(self, metadata: Dict) -> str:
        """Format metadata as string for prompt"""
        lines = []
        for key, value in metadata.items():
            lines.append(f"**{key}:** {value}")
        return "\n".join(lines)
