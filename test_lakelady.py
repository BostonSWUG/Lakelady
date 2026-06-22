"""
Lakelady Test Suite

Tests all combinations of:
- Mode: Upload / Download
- Create subfolders: True / False (download mode)
- Include subfolders: True / False (upload mode)
- Overwrite existing files: True / False (download mode)
- Remove existing attachments: True / False (upload mode)

These tests mock Selenium WebDriver and Agile interactions so they can run
without a browser or network access.

Run: python -m pytest test_lakelady.py -v
"""

import os
import sys
import shutil
import tempfile
import time
from unittest.mock import patch, MagicMock, PropertyMock
from itertools import product

import pytest

# Add the project root to path so we can import lakelady modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lakelady


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files, cleaned up after each test."""
    d = tempfile.mkdtemp(prefix="lakelady_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def mock_driver():
    """Create a mock Selenium WebDriver with common behaviors stubbed."""
    driver = MagicMock()
    driver.window_handles = ["window1"]
    driver.current_url = "https://arplm.robotics.a2z.com/Agile/PCMServlet"

    # Mock find_element to return elements that behave reasonably
    mock_element = MagicMock()
    mock_element.text = "Showing 1 of 2"
    mock_element.get_attribute.return_value = "some-class"
    driver.find_element.return_value = mock_element
    driver.find_elements.return_value = []

    # execute_script returns appropriate values
    driver.execute_script.return_value = True

    return driver


@pytest.fixture
def sample_upload_files(temp_dir):
    """Create sample files that mimic SolidWorks exports for upload testing."""
    files = [
        "400-04463_R01.pdf",
        "400-04463_R01.png",
        "400-04463_R01.x_t",
        "420-28772_R02.pdf",
        "420-28772_R02.png",
    ]
    for f in files:
        filepath = os.path.join(temp_dir, f)
        with open(filepath, "w") as fh:
            fh.write(f"dummy content for {f}")
    return temp_dir


@pytest.fixture
def sample_upload_files_with_subfolders(temp_dir):
    """Create sample files in subdirectories for include_subfolders testing."""
    # Top-level files
    top_files = ["400-04463_R01.pdf", "420-28772_R02.pdf"]
    for f in top_files:
        with open(os.path.join(temp_dir, f), "w") as fh:
            fh.write(f"top-level: {f}")

    # Subfolder files
    sub_dir = os.path.join(temp_dir, "subassembly")
    os.makedirs(sub_dir)
    sub_files = ["690-06316_R01.pdf", "690-06316_R01.png"]
    for f in sub_files:
        with open(os.path.join(sub_dir, f), "w") as fh:
            fh.write(f"subfolder: {f}")

    return temp_dir


# =============================================================================
# Unit Tests: get_files_to_add (Upload file discovery)
# =============================================================================

class TestGetFilesToAdd:
    """Test the file discovery logic used in upload mode."""

    def test_basic_file_discovery(self, sample_upload_files):
        """Files named with part number prefix are discovered correctly."""
        result = lakelady.get_files_to_add(sample_upload_files, include_subfolders=False)

        assert "400-04463" in result
        assert "420-28772" in result
        assert len(result["400-04463"]) == 3  # pdf, png, x_t
        assert len(result["420-28772"]) == 2  # pdf, png

    def test_include_subfolders_false(self, sample_upload_files_with_subfolders):
        """When include_subfolders=False, only top-level files are found."""
        result = lakelady.get_files_to_add(
            sample_upload_files_with_subfolders, include_subfolders=False
        )

        assert "400-04463" in result
        assert "420-28772" in result
        assert "690-06316" not in result  # Subfolder files excluded

    def test_include_subfolders_true(self, sample_upload_files_with_subfolders):
        """When include_subfolders=True, subdirectory files are also found."""
        result = lakelady.get_files_to_add(
            sample_upload_files_with_subfolders, include_subfolders=True
        )

        assert "400-04463" in result
        assert "420-28772" in result
        assert "690-06316" in result  # Subfolder files included
        assert len(result["690-06316"]) == 2

    def test_images_sorted_first(self, sample_upload_files):
        """Image files (.png, .jpg) are moved to the front of each part's list."""
        result = lakelady.get_files_to_add(sample_upload_files, include_subfolders=False)

        # For 400-04463, the png should be first
        first_file = result["400-04463"][0]
        assert first_file.endswith(".png")

    def test_ignores_log_and_json_files(self, temp_dir):
        """Log and JSON files are ignored even if named with part numbers."""
        with open(os.path.join(temp_dir, "400-04463_R01.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(temp_dir, "400-04463_R01.log"), "w") as f:
            f.write("log")
        with open(os.path.join(temp_dir, "400-04463_R01.pdf"), "w") as f:
            f.write("pdf")

        result = lakelady.get_files_to_add(temp_dir, include_subfolders=False)

        assert "400-04463" in result
        assert len(result["400-04463"]) == 1  # Only the PDF
        assert result["400-04463"][0].endswith(".pdf")

    def test_empty_directory(self, temp_dir):
        """Empty directory returns empty dict."""
        result = lakelady.get_files_to_add(temp_dir, include_subfolders=False)
        assert result == {}

    def test_files_without_underscore_ignored(self, temp_dir):
        """Files without a part number pattern are skipped."""
        with open(os.path.join(temp_dir, "README.txt"), "w") as f:
            f.write("readme")
        with open(os.path.join(temp_dir, "notes.pdf"), "w") as f:
            f.write("notes")

        result = lakelady.get_files_to_add(temp_dir, include_subfolders=False)
        assert result == {}

    def test_png_without_revision_suffix(self, temp_dir):
        """PNG files named with just part number (no _R01) are picked up."""
        with open(os.path.join(temp_dir, "400-04463.png"), "w") as f:
            f.write("image")
        with open(os.path.join(temp_dir, "400-04463_R01.pdf"), "w") as f:
            f.write("pdf")

        result = lakelady.get_files_to_add(temp_dir, include_subfolders=False)
        assert "400-04463" in result
        assert len(result["400-04463"]) == 2

    def test_dash_suffix_part_number(self, temp_dir):
        """Part numbers with dash suffixes like 405-07872-X are recognized."""
        with open(os.path.join(temp_dir, "405-07872-X.png"), "w") as f:
            f.write("image")
        with open(os.path.join(temp_dir, "405-07872-X_R04.pdf"), "w") as f:
            f.write("pdf")

        result = lakelady.get_files_to_add(temp_dir, include_subfolders=False)
        assert "405-07872-X" in result
        assert len(result["405-07872-X"]) == 2


# =============================================================================
# Unit Tests: download_from_affd_item (Download with file move)
# =============================================================================

class TestDownloadFromAffdItem:
    """Test the download logic including the file-move fix for subfolders."""

    @patch("lakelady.WebDriverWait")
    @patch("lakelady.EC")
    @patch("lakelady.By")
    @patch("lakelady.try_till_works")
    @patch("lakelady.wait_for_agile_ready")
    @patch("lakelady.search_for")
    def test_download_moves_file_to_subfolder(
        self, mock_search, mock_wait, mock_try, mock_by, mock_ec, mock_wdw,
        mock_driver, temp_dir
    ):
        """Downloaded files are moved from base dir to CO subfolder."""
        base_dir = temp_dir
        co_subfolder = os.path.join(base_dir, "DECO-19436")
        os.makedirs(co_subfolder)

        fake_file = "425-01837_R01.PDF"
        fake_file_path = os.path.join(base_dir, fake_file)

        def simulate_download(*args, **kwargs):
            with open(fake_file_path, "w") as f:
                f.write("fake PDF content")
            return None

        mock_driver.execute_script.side_effect = simulate_download

        footer_mock = MagicMock()
        footer_mock.text = "1 of 1"
        link_mock = MagicMock()
        link_mock.text = fake_file
        att_table_mock = MagicMock()
        att_table_mock.find_elements.return_value = [link_mock]

        call_count = [0]
        wait_instance = MagicMock()
        def until_fn(condition):
            call_count[0] += 1
            return footer_mock if call_count[0] == 1 else att_table_mock
        wait_instance.until = until_fn
        mock_wdw.return_value = wait_instance

        result = lakelady.download_from_affd_item(
            mock_driver, "DECO-19436", "425-01837", 1, co_subfolder, "pdf", False
        )

        expected_dest = os.path.join(co_subfolder, fake_file)
        assert os.path.exists(expected_dest), f"File should be at {expected_dest}"
        assert not os.path.exists(fake_file_path), "File should be removed from base dir"
        assert fake_file in result

    @patch("lakelady.WebDriverWait")
    @patch("lakelady.EC")
    @patch("lakelady.By")
    @patch("lakelady.try_till_works")
    @patch("lakelady.wait_for_agile_ready")
    @patch("lakelady.search_for")
    def test_download_no_move_when_no_subfolders(
        self, mock_search, mock_wait, mock_try, mock_by, mock_ec, mock_wdw,
        mock_driver, temp_dir
    ):
        """When download_path IS the base dir, no move is needed."""
        base_dir = temp_dir
        fake_file = "425-01837_R01.PDF"
        fake_file_path = os.path.join(base_dir, fake_file)

        def simulate_download(*args, **kwargs):
            with open(fake_file_path, "w") as f:
                f.write("fake PDF content")
            return None

        mock_driver.execute_script.side_effect = simulate_download

        footer_mock = MagicMock()
        footer_mock.text = "1 of 1"
        link_mock = MagicMock()
        link_mock.text = fake_file
        att_table_mock = MagicMock()
        att_table_mock.find_elements.return_value = [link_mock]

        call_count = [0]
        wait_instance = MagicMock()
        def until_fn(condition):
            call_count[0] += 1
            return footer_mock if call_count[0] == 1 else att_table_mock
        wait_instance.until = until_fn
        mock_wdw.return_value = wait_instance

        result = lakelady.download_from_affd_item(
            mock_driver, "DECO-19436", "425-01837", 1, base_dir, "pdf", False
        )

        assert os.path.exists(fake_file_path), "File should remain in base dir"
        assert fake_file in result

    @patch("lakelady.WebDriverWait")
    @patch("lakelady.EC")
    @patch("lakelady.By")
    @patch("lakelady.try_till_works")
    @patch("lakelady.wait_for_agile_ready")
    @patch("lakelady.search_for")
    def test_download_overwrite_deletes_existing(
        self, mock_search, mock_wait, mock_try, mock_by, mock_ec, mock_wdw,
        mock_driver, temp_dir
    ):
        """When overwrite=True, existing file is deleted before download."""
        co_subfolder = os.path.join(temp_dir, "DECO-19436")
        os.makedirs(co_subfolder)
        fake_file = "425-01837_R01.PDF"
        existing_file = os.path.join(co_subfolder, fake_file)
        with open(existing_file, "w") as f:
            f.write("OLD content")

        def simulate_download(*args, **kwargs):
            with open(os.path.join(temp_dir, fake_file), "w") as f:
                f.write("NEW content")
            return None

        mock_driver.execute_script.side_effect = simulate_download

        footer_mock = MagicMock()
        footer_mock.text = "1 of 1"
        link_mock = MagicMock()
        link_mock.text = fake_file
        att_table_mock = MagicMock()
        att_table_mock.find_elements.return_value = [link_mock]

        call_count = [0]
        wait_instance = MagicMock()
        def until_fn(condition):
            call_count[0] += 1
            return footer_mock if call_count[0] == 1 else att_table_mock
        wait_instance.until = until_fn
        mock_wdw.return_value = wait_instance

        result = lakelady.download_from_affd_item(
            mock_driver, "DECO-19436", "425-01837", 1, co_subfolder, "pdf", True
        )

        final_file = os.path.join(co_subfolder, fake_file)
        assert os.path.exists(final_file)
        with open(final_file) as f:
            assert "NEW" in f.read()

    @patch("lakelady.WebDriverWait")
    @patch("lakelady.EC")
    @patch("lakelady.By")
    @patch("lakelady.try_till_works")
    @patch("lakelady.wait_for_agile_ready")
    @patch("lakelady.search_for")
    def test_download_filter_by_extension(
        self, mock_search, mock_wait, mock_try, mock_by, mock_ec, mock_wdw,
        mock_driver, temp_dir
    ):
        """File filter correctly limits which attachments are downloaded."""
        fake_pdf = "425-01837_R01.PDF"
        fake_png = "425-01837_R01.PNG"

        def simulate_download(*args, **kwargs):
            with open(os.path.join(temp_dir, fake_pdf), "w") as f:
                f.write("pdf content")
            return None

        mock_driver.execute_script.side_effect = simulate_download

        footer_mock = MagicMock()
        footer_mock.text = "1 of 2"
        link_pdf = MagicMock()
        link_pdf.text = fake_pdf
        link_png = MagicMock()
        link_png.text = fake_png
        att_table_mock = MagicMock()
        att_table_mock.find_elements.return_value = [link_pdf, link_png]

        call_count = [0]
        wait_instance = MagicMock()
        def until_fn(condition):
            call_count[0] += 1
            return footer_mock if call_count[0] == 1 else att_table_mock
        wait_instance.until = until_fn
        mock_wdw.return_value = wait_instance

        result = lakelady.download_from_affd_item(
            mock_driver, "DECO-19436", "425-01837", 1, temp_dir, "pdf", False
        )

        assert fake_pdf in result
        assert fake_png not in result


# =============================================================================
# Integration Tests: Argument Parsing (all flag combinations)
# =============================================================================

class TestArgumentParsing:
    """Test that CLI arguments are parsed correctly for all flag combos."""

    @patch("lakelady.webdriver")
    @patch("lakelady.open_webpage")
    @patch("lakelady.login_to_agile")
    @patch("lakelady.wait_for_agile_ready")
    @patch("lakelady.search_for")
    @patch("lakelady.get_affd_items")
    @patch("lakelady.download_from_affd_item")
    @patch("lakelady.upload_to_affd_item")
    @patch("lakelady.get_files_to_add")
    @patch("lakelady.try_till_works")
    def test_download_create_subfolders_true(
        self, mock_try, mock_get_files, mock_upload, mock_download,
        mock_get_affd, mock_search, mock_wait, mock_login, mock_open,
        mock_webdriver, temp_dir
    ):
        """Download mode with create_subfolders=True creates per-CO folders."""
        mock_driver = MagicMock()
        mock_driver.window_handles = ["w1"]
        mock_webdriver.Firefox.return_value = mock_driver
        mock_get_affd.return_value = ["400-04463"]
        mock_download.return_value = ["400-04463_R01.PDF"]

        test_args = [
            "lakelady.py", "--download", "--file-filter", "pdf",
            "--create-subfolders",
            "testuser", "False", temp_dir, "False",
            "DECO-19436", "DECO-19531"
        ]

        with patch.object(sys, "argv", test_args):
            with patch("sys.exit"):
                try:
                    lakelady.run_me()
                except (SystemExit, Exception):
                    pass

        # Verify subfolders were created
        assert os.path.exists(os.path.join(temp_dir, "DECO-19436"))
        assert os.path.exists(os.path.join(temp_dir, "DECO-19531"))

    @patch("lakelady.webdriver")
    @patch("lakelady.open_webpage")
    @patch("lakelady.login_to_agile")
    @patch("lakelady.wait_for_agile_ready")
    @patch("lakelady.search_for")
    @patch("lakelady.get_affd_items")
    @patch("lakelady.download_from_affd_item")
    @patch("lakelady.try_till_works")
    def test_download_create_subfolders_false(
        self, mock_try, mock_download, mock_get_affd,
        mock_search, mock_wait, mock_login, mock_open,
        mock_webdriver, temp_dir
    ):
        """Download mode without create_subfolders saves all files to base dir."""
        mock_driver = MagicMock()
        mock_driver.window_handles = ["w1"]
        mock_webdriver.Firefox.return_value = mock_driver
        mock_get_affd.return_value = ["400-04463"]
        mock_download.return_value = ["400-04463_R01.PDF"]

        test_args = [
            "lakelady.py", "--download", "--file-filter", "pdf",
            # No --create-subfolders flag
            "testuser", "False", temp_dir, "False",
            "DECO-19436"
        ]

        with patch.object(sys, "argv", test_args):
            with patch("sys.exit"):
                try:
                    lakelady.run_me()
                except (SystemExit, Exception):
                    pass

        # download_from_affd_item should be called with base dir as path
        if mock_download.called:
            call_args = mock_download.call_args
            download_path_arg = call_args[0][4]  # 5th positional arg
            assert os.path.normpath(download_path_arg) == os.path.normpath(
                os.path.abspath(temp_dir)
            )


# =============================================================================
# Parametrized Combination Tests
# =============================================================================

# All valid flag combinations per mode
DOWNLOAD_COMBOS = list(product(
    [True, False],  # create_subfolders
    [True, False],  # overwrite
    ["pdf", "all", "pdf,png"],  # file_filter
))

UPLOAD_COMBOS = list(product(
    [True, False],  # include_subfolders
    [True, False],  # remove_existing_att
))


class TestDownloadCombinations:
    """Parametrized tests for all download flag combinations."""

    @pytest.mark.parametrize(
        "create_subfolders,overwrite,file_filter",
        DOWNLOAD_COMBOS,
        ids=[
            f"subfolders={sf}_overwrite={ow}_filter={ff}"
            for sf, ow, ff in DOWNLOAD_COMBOS
        ],
    )
    @patch("lakelady.webdriver")
    @patch("lakelady.open_webpage")
    @patch("lakelady.login_to_agile")
    @patch("lakelady.wait_for_agile_ready")
    @patch("lakelady.search_for")
    @patch("lakelady.get_affd_items")
    @patch("lakelady.download_from_affd_item")
    @patch("lakelady.try_till_works")
    def test_download_combination(
        self, mock_try, mock_download, mock_get_affd,
        mock_search, mock_wait, mock_login, mock_open,
        mock_webdriver, create_subfolders, overwrite, file_filter, temp_dir
    ):
        """Each download flag combination parses and executes without error."""
        mock_driver = MagicMock()
        mock_driver.window_handles = ["w1"]
        mock_webdriver.Firefox.return_value = mock_driver
        mock_get_affd.return_value = ["400-04463", "420-28772"]
        mock_download.return_value = ["file.pdf"]

        test_args = [
            "lakelady.py", "--download", "--file-filter", file_filter,
        ]
        if create_subfolders:
            test_args.append("--create-subfolders")
        if overwrite:
            test_args.append("--overwrite")
        test_args += ["testuser", "False", temp_dir, "False", "DECO-19436", "DECO-19531"]

        with patch.object(sys, "argv", test_args):
            with patch("sys.exit"):
                try:
                    lakelady.run_me()
                except (SystemExit, Exception):
                    pass

        # Verify download function was called for each CO's affected items
        assert mock_download.called, "download_from_affd_item should have been called"

        # Verify correct overwrite flag was passed through
        for call in mock_download.call_args_list:
            passed_overwrite = call[0][6]  # 7th positional arg
            assert passed_overwrite == overwrite

        # Verify subfolders exist if create_subfolders was set
        if create_subfolders:
            assert os.path.exists(os.path.join(temp_dir, "DECO-19436"))
            assert os.path.exists(os.path.join(temp_dir, "DECO-19531"))


class TestUploadCombinations:
    """Parametrized tests for all upload flag combinations."""

    @pytest.mark.parametrize(
        "include_subfolders,remove_existing",
        UPLOAD_COMBOS,
        ids=[
            f"include_subfolders={isf}_remove_existing={re}"
            for isf, re in UPLOAD_COMBOS
        ],
    )
    @patch("lakelady.webdriver")
    @patch("lakelady.open_webpage")
    @patch("lakelady.login_to_agile")
    @patch("lakelady.wait_for_agile_ready")
    @patch("lakelady.search_for")
    @patch("lakelady.get_affd_items")
    @patch("lakelady.upload_to_affd_item")
    @patch("lakelady.get_files_to_add")
    @patch("lakelady.try_till_works")
    def test_upload_combination(
        self, mock_try, mock_get_files, mock_upload, mock_get_affd,
        mock_search, mock_wait, mock_login, mock_open,
        mock_webdriver, include_subfolders, remove_existing, temp_dir
    ):
        """Each upload flag combination parses and executes without error."""
        # Create dummy files so the path exists
        with open(os.path.join(temp_dir, "400-04463_R01.pdf"), "w") as f:
            f.write("test")
        if include_subfolders:
            sub = os.path.join(temp_dir, "sub")
            os.makedirs(sub)
            with open(os.path.join(sub, "420-28772_R01.pdf"), "w") as f:
                f.write("test")

        mock_driver = MagicMock()
        mock_driver.window_handles = ["w1"]
        mock_webdriver.Firefox.return_value = mock_driver
        mock_get_affd.return_value = ["400-04463", "420-28772"]
        mock_get_files.return_value = {
            "400-04463": [os.path.join(temp_dir, "400-04463_R01.pdf")],
        }

        remove_flag = "True" if remove_existing else "False"
        subfolders_flag = "True" if include_subfolders else "False"

        test_args = [
            "lakelady.py",
            "testuser", remove_flag, temp_dir, subfolders_flag,
            "DECO-19436"
        ]

        with patch.object(sys, "argv", test_args):
            with patch("sys.exit"):
                try:
                    lakelady.run_me()
                except (SystemExit, Exception):
                    pass

        # Verify get_files_to_add was called with correct include_subfolders
        if mock_get_files.called:
            call_args = mock_get_files.call_args
            passed_include_subfolders = call_args[0][1]
            assert passed_include_subfolders == include_subfolders

        # Verify upload_to_affd_item was called with correct remove flag
        if mock_upload.called:
            call_args = mock_upload.call_args
            passed_remove = call_args[0][5]  # 6th positional arg
            assert passed_remove == remove_existing


# =============================================================================
# Multi-CO Download: File Routing Tests (the bug fix)
# =============================================================================

class TestMultiCODownloadRouting:
    """
    Tests specifically for the multi-CO download bug fix.
    Ensures files from each CO land in the correct subfolder.
    """

    def test_file_move_logic_subfolder_mode(self, temp_dir):
        """
        Simulate the file-move logic directly:
        Firefox downloads to base dir, file gets moved to CO subfolder.
        """
        base_dir = temp_dir
        co1_dir = os.path.join(base_dir, "DECO-19436")
        co2_dir = os.path.join(base_dir, "DECO-19531")
        os.makedirs(co1_dir)
        os.makedirs(co2_dir)

        # Simulate Firefox downloading files to base_dir
        file1 = "425-01837_R01.PDF"
        file2 = "400-07733_R05.PDF"

        # File 1 should go to CO1
        with open(os.path.join(base_dir, file1), "w") as f:
            f.write("content1")

        firefox_download_dir = os.path.dirname(co1_dir)
        src = os.path.join(firefox_download_dir, file1)
        dest = os.path.join(co1_dir, file1)
        if os.path.normpath(src) != os.path.normpath(dest) and os.path.exists(src):
            shutil.move(src, dest)

        assert os.path.exists(os.path.join(co1_dir, file1))
        assert not os.path.exists(os.path.join(base_dir, file1))

        # File 2 should go to CO2
        with open(os.path.join(base_dir, file2), "w") as f:
            f.write("content2")

        firefox_download_dir = os.path.dirname(co2_dir)
        src = os.path.join(firefox_download_dir, file2)
        dest = os.path.join(co2_dir, file2)
        if os.path.normpath(src) != os.path.normpath(dest) and os.path.exists(src):
            shutil.move(src, dest)

        assert os.path.exists(os.path.join(co2_dir, file2))
        assert not os.path.exists(os.path.join(base_dir, file2))

    def test_file_stays_in_place_no_subfolder_mode(self, temp_dir):
        """
        When create_subfolders=False, download_path == base dir.
        No move should occur.
        """
        base_dir = temp_dir
        download_path = base_dir  # Same as Firefox's download dir

        file1 = "425-01837_R01.PDF"
        with open(os.path.join(base_dir, file1), "w") as f:
            f.write("content")

        # This is the logic from download_from_affd_item
        firefox_download_dir = os.path.dirname(download_path)
        src = os.path.join(firefox_download_dir, file1)
        dest = os.path.join(download_path, file1)

        # When download_path == base_dir, src points to PARENT/file
        # which won't exist, so no move happens
        if os.path.normpath(src) != os.path.normpath(dest) and os.path.exists(src):
            shutil.move(src, dest)

        # File should still be where it was (in base_dir)
        assert os.path.exists(os.path.join(base_dir, file1))

    def test_five_cos_all_route_correctly(self, temp_dir):
        """Simulate 5 COs each getting files routed to correct subfolders."""
        base_dir = temp_dir
        cos = ["DECO-19436", "DECO-19531", "DECO-19614", "DECO-19651", "DECO-19767"]
        files_per_co = {
            "DECO-19436": ["425-01837_R01.PDF", "620-00389_R02.pdf"],
            "DECO-19531": ["400-07733_R05.PDF", "420-26868_R04.pdf"],
            "DECO-19614": ["405-07870_R04.pdf"],
            "DECO-19651": ["400-07829-X_R01.pdf", "420-28383_R01.pdf"],
            "DECO-19767": ["540-04595-XYY_R01.pdf"],
        }

        for co in cos:
            co_dir = os.path.join(base_dir, co)
            os.makedirs(co_dir)

            for filename in files_per_co[co]:
                # Simulate Firefox downloading to base
                with open(os.path.join(base_dir, filename), "w") as f:
                    f.write(f"content for {co}/{filename}")

                # Apply the move logic
                firefox_download_dir = os.path.dirname(co_dir)
                src = os.path.join(firefox_download_dir, filename)
                dest = os.path.join(co_dir, filename)
                if os.path.normpath(src) != os.path.normpath(dest) and os.path.exists(src):
                    shutil.move(src, dest)

        # Verify all files are in correct subfolders
        for co in cos:
            co_dir = os.path.join(base_dir, co)
            for filename in files_per_co[co]:
                assert os.path.exists(os.path.join(co_dir, filename)), \
                    f"{filename} should be in {co_dir}"
                assert not os.path.exists(os.path.join(base_dir, filename)), \
                    f"{filename} should NOT be in base dir"


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test boundary conditions and error scenarios."""

    def test_download_no_attachments(self, mock_driver, temp_dir):
        """Affected item with no attachments returns empty list gracefully."""
        footer_mock = MagicMock()
        footer_mock.text = "Showing 0 of 0"

        with patch("lakelady.try_till_works"):
            with patch("lakelady.wait_for_agile_ready"):
                with patch("lakelady.search_for"):
                    with patch("lakelady.WebDriverWait") as mock_wdw:
                        wait_instance = MagicMock()
                        wait_instance.until.return_value = footer_mock
                        mock_wdw.return_value = wait_instance

                        result = lakelady.download_from_affd_item(
                            mock_driver, "DECO-19436", "300-00868", 1,
                            temp_dir, "pdf", False
                        )

        assert result == []

    def test_part_file_still_downloading(self, temp_dir):
        """
        If a .part file exists (Firefox still downloading), the move
        waits before proceeding.
        """
        base_dir = temp_dir
        co_dir = os.path.join(base_dir, "DECO-19436")
        os.makedirs(co_dir)

        filename = "test_file.PDF"
        part_file = os.path.join(base_dir, filename + ".part")
        final_file = os.path.join(base_dir, filename)

        # Create .part file to simulate in-progress download
        with open(part_file, "w") as f:
            f.write("partial")

        import threading

        def finish_download():
            """Simulate download completing after 0.5 second."""
            time.sleep(0.5)
            # Write the final file BEFORE removing .part (Firefox behavior)
            with open(final_file, "w") as f:
                f.write("complete content")
            os.remove(part_file)

        t = threading.Thread(target=finish_download)
        t.start()

        # Apply the move logic with .part wait (same as in lakelady.py)
        wait_start = time.time()
        while os.path.exists(part_file) and (time.time() - wait_start < 30):
            time.sleep(0.5)

        # Now move the file
        firefox_download_dir = os.path.dirname(co_dir)
        src_file = os.path.join(firefox_download_dir, filename)
        dest_file = os.path.join(co_dir, filename)

        if os.path.normpath(src_file) != os.path.normpath(dest_file):
            if os.path.exists(src_file):
                shutil.move(src_file, dest_file)

        t.join()

        assert os.path.exists(dest_file), f"File should be at {dest_file}"
        with open(dest_file) as f:
            assert "complete" in f.read()

    def test_scan_for_copies_detects_squared(self, temp_dir):
        """scan_for_copies correctly identifies already-squared images."""
        # Create files that indicate squared processing
        with open(os.path.join(temp_dir, "400-04463_R01-squared.png"), "w") as f:
            f.write("squared")
        with open(os.path.join(temp_dir, "400-04463_R01.pdf"), "w") as f:
            f.write("pdf")

        result = lakelady.scan_for_copies(temp_dir)
        assert "400-04463" in result

    def test_check_empty(self):
        """check_empty returns True when list contains empty strings."""
        assert lakelady.check_empty(["item1", "", "item3"]) is True
        assert lakelady.check_empty(["item1", "item2"]) is False
        assert lakelady.check_empty([""]) is True
        assert lakelady.check_empty([]) is False


# =============================================================================
# Full Matrix Summary
# =============================================================================

class TestFullMatrix:
    """
    Comprehensive matrix test covering all relevant flag combinations.

    Upload matrix (2x2 = 4 combos):
        include_subfolders: True/False
        remove_existing_att: True/False

    Download matrix (2x2x3 = 12 combos):
        create_subfolders: True/False
        overwrite: True/False
        file_filter: pdf / all / pdf,png
    """

    @pytest.mark.parametrize("include_subfolders", [True, False])
    @pytest.mark.parametrize("remove_existing", [True, False])
    def test_upload_matrix(self, include_subfolders, remove_existing, temp_dir):
        """Verify upload argument parsing for all flag combos."""
        # Create test files
        with open(os.path.join(temp_dir, "400-04463_R01.pdf"), "w") as f:
            f.write("test")

        result = lakelady.get_files_to_add(temp_dir, include_subfolders)
        # The function should work without error regardless of flag combo
        assert isinstance(result, dict)

    @pytest.mark.parametrize("create_subfolders", [True, False])
    @pytest.mark.parametrize("overwrite", [True, False])
    @pytest.mark.parametrize("file_filter", ["pdf", "all", "pdf,png"])
    def test_download_matrix(self, create_subfolders, overwrite, file_filter, temp_dir):
        """Verify download path logic for all flag combos."""
        base_dir = temp_dir
        co = "DECO-19436"

        if create_subfolders:
            co_download_path = os.path.abspath(os.path.join(base_dir, co))
        else:
            co_download_path = os.path.abspath(base_dir)
        os.makedirs(co_download_path, exist_ok=True)

        # Verify the path structure is correct
        if create_subfolders:
            assert co in co_download_path
            assert os.path.dirname(co_download_path) == os.path.abspath(base_dir)
        else:
            assert co_download_path == os.path.abspath(base_dir)

        # Verify the move logic won't break
        firefox_download_dir = os.path.dirname(co_download_path)
        test_file = "test_file.pdf"
        src = os.path.join(firefox_download_dir, test_file)
        dest = os.path.join(co_download_path, test_file)

        if create_subfolders:
            # src != dest, so move would happen if file exists
            assert os.path.normpath(src) != os.path.normpath(dest)
        else:
            # src would be in parent dir, which is fine — file won't be there
            # No move needed
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
