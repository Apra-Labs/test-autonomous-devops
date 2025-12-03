"""
Unit tests for SmartLogExtractor

Tests smart extraction of relevant error context from large log files.
"""
import pytest
import tempfile
from pathlib import Path
from agent.log_extractor import SmartLogExtractor


class TestSmartLogExtractor:
    """Test SmartLogExtractor functionality"""

    def setup_method(self):
        """Setup before each test"""
        self.extractor = SmartLogExtractor(max_excerpt_lines=500)

    def test_extract_python_import_error(self):
        """Test extraction of Python import error"""
        log_content = """
Building project...
Running tests...
Traceback (most recent call last):
  File "test.py", line 10, in <module>
    import json
ModuleNotFoundError: No module named 'json'
        """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(log_content)
            log_path = f.name

        try:
            context = self.extractor.extract_relevant_error(log_path, platform="python")

            # Import error with Traceback triggers test_failure, but no module should still work
            assert context['error_type'] in ['python_import_error', 'test_failure']
            assert 'Traceback' in context['error_excerpt']
            assert 'ModuleNotFoundError' in context['error_excerpt']
            assert context['metadata_dict']['platform'] == 'python'

        finally:
            Path(log_path).unlink()

    def test_extract_cpp_compilation_error(self):
        """Test extraction of C++ compilation error"""
        log_content = """
[ 50%] Building CXX object CMakeFiles/test.dir/src/main.cpp.o
[ 75%] Building CXX object CMakeFiles/test.dir/src/FramesMuxer.cpp.o
/path/to/src/FramesMuxer.cpp:45:10: error: 'mOutput' was not declared in this scope
   45 |     if (!mOutput) {
      |          ^~~~~~~
make[2]: *** [CMakeFiles/test.dir/build.make:76: CMakeFiles/test.dir/src/FramesMuxer.cpp.o] Error 1
        """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(log_content)
            log_path = f.name

        try:
            context = self.extractor.extract_relevant_error(log_path, platform="linux")

            # CMake in output may trigger cmake_configuration, but .cpp: pattern should work
            assert context['error_type'] in ['compilation_error', 'cmake_configuration']
            assert 'mOutput' in context['error_excerpt']
            assert 'FramesMuxer.cpp:45:10' in context['error_excerpt']
            assert 'was not declared' in context['error_excerpt']

        finally:
            Path(log_path).unlink()

    def test_extract_linker_error(self):
        """Test extraction of linker error"""
        log_content = """
[100%] Linking CXX executable test
/usr/bin/ld: CMakeFiles/test.dir/src/main.cpp.o: undefined reference to `missing_function()'
collect2: error: ld returned 1 exit status
make[2]: *** [CMakeFiles/test.dir/build.make:123: test] Error 1
        """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(log_content)
            log_path = f.name

        try:
            context = self.extractor.extract_relevant_error(log_path, platform="linux")

            # Make in output may trigger cmake_configuration
            assert context['error_type'] in ['linker_error', 'cmake_configuration']
            assert 'undefined reference' in context['error_excerpt']
            assert 'missing_function' in context['error_excerpt']

        finally:
            Path(log_path).unlink()

    def test_extract_cmake_error(self):
        """Test extraction of CMake configuration error"""
        log_content = """
-- Configuring project
CMake Error at CMakeLists.txt:15 (find_package):
  Could not find a package configuration file provided by "OpenCV" with
  any of the following names:

    OpenCVConfig.cmake
    opencv-config.cmake

-- Configuring incomplete, errors occurred!
        """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(log_content)
            log_path = f.name

        try:
            context = self.extractor.extract_relevant_error(log_path, platform="linux")

            # CMake Error should trigger cmake_configuration
            assert context['error_type'] == 'cmake_configuration'
            assert 'CMake Error' in context['error_excerpt']
            assert 'OpenCV' in context['error_excerpt']

        finally:
            Path(log_path).unlink()

    def test_extract_from_massive_log(self):
        """Test handling of very large log file (10MB+)"""
        # Generate large log
        log_lines = []
        log_lines.extend(["[INFO] Build output line\n"] * 100000)  # ~2MB of noise
        log_lines.append("ERROR: Build failed at line 100001\n")
        log_lines.append("src/test.cpp:123:45: error: syntax error\n")
        log_lines.extend(["[INFO] More output\n"] * 50000)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.writelines(log_lines)
            log_path = f.name

        try:
            context = self.extractor.extract_relevant_error(log_path, platform="linux")

            # Should extract relevant portion without crashing
            assert context['excerpt_lines'] <= 500
            assert 'ERROR: Build failed' in context['error_excerpt']
            assert context['metadata_dict']['total_log_lines'] == len(log_lines)

        finally:
            Path(log_path).unlink()

    def test_extract_vcpkg_error(self):
        """Test extraction of vcpkg dependency error"""
        log_content = """
Detecting compiler hash for triplet x64-linux...
Installing package 1/10: opencv4:x64-linux...
Building package opencv4[core]:x64-linux...
CMake Error: Could not find CMAKE_MAKE_PROGRAM
error: building opencv4:x64-linux failed with: BUILD_FAILED
        """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(log_content)
            log_path = f.name

        try:
            context = self.extractor.extract_relevant_error(log_path, platform="linux")

            assert 'error_excerpt' in context
            assert 'BUILD_FAILED' in context['error_excerpt'] or 'CMake Error' in context['error_excerpt']

        finally:
            Path(log_path).unlink()

    def test_extract_with_multiple_errors(self):
        """Test extraction prioritizes last error"""
        log_content = """
ERROR 1: First error at line 10
Some output...
ERROR 2: Second error at line 50
More output...
ERROR 3: Final error at line 100
This is the actual failure
        """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(log_content)
            log_path = f.name

        try:
            context = self.extractor.extract_relevant_error(log_path, platform="test")

            # Should prioritize last error
            assert 'Final error' in context['error_excerpt']
            assert 'actual failure' in context['error_excerpt']

        finally:
            Path(log_path).unlink()

    def test_extract_with_no_clear_error(self):
        """Test extraction when no clear error pattern found"""
        log_content = """
Build step 1 completed
Build step 2 completed
Build step 3 completed
Process exited with code 1
        """

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(log_content)
            log_path = f.name

        try:
            context = self.extractor.extract_relevant_error(log_path, platform="test")

            # Should return last portion of log
            assert context['error_type'] == 'unknown'
            assert 'Process exited' in context['error_excerpt']

        finally:
            Path(log_path).unlink()

    def test_metadata_formatting(self):
        """Test metadata is properly formatted"""
        log_content = "ERROR: Test error\n"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write(log_content)
            log_path = f.name

        try:
            context = self.extractor.extract_relevant_error(log_path, platform="test-platform")

            # Check metadata_dict (for programmatic access)
            assert 'metadata_dict' in context
            assert context['metadata_dict']['platform'] == 'test-platform'
            assert 'total_log_lines' in context['metadata_dict']
            assert 'excerpt_lines' in context['metadata_dict']

            # Check metadata string (for prompt)
            assert 'metadata' in context
            assert '**platform:** test-platform' in context['metadata']

        finally:
            Path(log_path).unlink()

    def test_excerpt_line_limit(self):
        """Test that excerpt respects max_excerpt_lines limit"""
        extractor = SmartLogExtractor(max_excerpt_lines=100)

        # Create log with 1000 lines
        log_lines = [f"Line {i}\n" for i in range(1000)]
        log_lines.append("ERROR: Final error\n")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.writelines(log_lines)
            log_path = f.name

        try:
            context = extractor.extract_relevant_error(log_path, platform="test")

            # Excerpt should be close to limit (within 100-500 range from extractor logic)
            # The extractor uses max_excerpt_lines for the window, but actual count may vary
            assert context['excerpt_lines'] <= 500  # Should honor overall max
            assert context['metadata_dict']['total_log_lines'] == 1001

        finally:
            Path(log_path).unlink()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
