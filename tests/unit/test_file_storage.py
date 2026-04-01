"""Unit tests for backend/utils/file_storage.py"""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.utils.file_storage import (
    delete_uploaded_file,
    get_file_hash,
    get_file_hash_from_bytes,
    sanitize_filename,
    save_temp_file,
    save_uploaded_file,
)


# ── sanitize_filename ──────────────────────────────────────────────────────────

class TestSanitizeFilename:
    @pytest.mark.parametrize("char", ['<', '>', ':', '"', '/', '\\', '|', '?', '*'])
    def test_replaces_unsafe_characters(self, char):
        result = sanitize_filename(f"file{char}name.pdf")
        assert char not in result
        assert "_" in result

    def test_strips_directory_path(self):
        result = sanitize_filename("/some/path/to/file.pdf")
        assert "/" not in result
        assert result == "file.pdf"

    def test_windows_path_stripped(self):
        result = sanitize_filename("C:\\Users\\test\\file.pdf")
        assert "\\" not in result

    def test_long_filename_truncated(self):
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        assert len(result) <= 255

    def test_extension_preserved_on_truncation(self):
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name)
        assert result.endswith(".pdf")

    def test_normal_filename_unchanged(self):
        result = sanitize_filename("my_paper_2024.pdf")
        assert result == "my_paper_2024.pdf"

    def test_empty_string(self):
        result = sanitize_filename("")
        assert isinstance(result, str)


# ── get_file_hash_from_bytes ───────────────────────────────────────────────────

class TestGetFileHashFromBytes:
    def test_returns_64_char_hex_string(self):
        result = get_file_hash_from_bytes(b"hello world")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_bytes_same_hash(self):
        data = b"test content"
        assert get_file_hash_from_bytes(data) == get_file_hash_from_bytes(data)

    def test_different_bytes_different_hash(self):
        assert get_file_hash_from_bytes(b"aaa") != get_file_hash_from_bytes(b"bbb")

    def test_empty_bytes(self):
        result = get_file_hash_from_bytes(b"")
        # SHA-256 of empty string is well-known
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


# ── get_file_hash (from file path) ─────────────────────────────────────────────

class TestGetFileHash:
    def test_matches_bytes_hash(self, tmp_path):
        data = b"file content for hashing"
        p = tmp_path / "test.pdf"
        p.write_bytes(data)
        assert get_file_hash(str(p)) == get_file_hash_from_bytes(data)

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            get_file_hash("/nonexistent/path/to/file.pdf")


# ── save_temp_file ─────────────────────────────────────────────────────────────

class TestSaveTempFile:
    def test_creates_file_with_content(self):
        data = b"%PDF-1.4 test content"
        path = save_temp_file(data)
        try:
            assert os.path.exists(path)
            assert open(path, "rb").read() == data
        finally:
            os.unlink(path)

    def test_default_suffix_is_pdf(self):
        path = save_temp_file(b"data")
        try:
            assert path.endswith(".pdf")
        finally:
            os.unlink(path)

    def test_custom_suffix(self):
        path = save_temp_file(b"data", suffix=".txt")
        try:
            assert path.endswith(".txt")
        finally:
            os.unlink(path)


# ── delete_uploaded_file ───────────────────────────────────────────────────────

class TestDeleteUploadedFile:
    def test_deletes_existing_file(self, tmp_path):
        p = tmp_path / "todelete.pdf"
        p.write_bytes(b"content")
        assert delete_uploaded_file(str(p)) is True
        assert not p.exists()

    def test_returns_false_for_missing_file(self):
        assert delete_uploaded_file("/nonexistent/file.pdf") is False

    def test_handles_permission_error_gracefully(self, tmp_path):
        p = tmp_path / "readonly.pdf"
        p.write_bytes(b"content")
        with patch("os.remove", side_effect=PermissionError("access denied")):
            result = delete_uploaded_file(str(p))
        assert result is False


# ── save_uploaded_file ─────────────────────────────────────────────────────────

class TestSaveUploadedFile:
    def test_saves_file_to_upload_dir(self, tmp_path):
        with patch("backend.utils.file_storage.settings") as mock_settings:
            mock_settings.UPLOAD_DIR = str(tmp_path)
            path = save_uploaded_file(b"PDF content", "test.pdf", source="upload")

        assert os.path.exists(path)
        assert open(path, "rb").read() == b"PDF content"

    def test_sanitizes_filename(self, tmp_path):
        with patch("backend.utils.file_storage.settings") as mock_settings:
            mock_settings.UPLOAD_DIR = str(tmp_path)
            path = save_uploaded_file(b"data", "bad:name?.pdf", source="upload")

        # The saved file should not contain the unsafe characters
        assert ":" not in os.path.basename(path)
        assert "?" not in os.path.basename(path)
