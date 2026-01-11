"""
Tests for the centralized cache directory system.
"""

import importlib
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from notte_core.common.cache import (
    CacheDirectory,
    check_for_legacy_data,
    ensure_cache_directory,
    get_cache_info,
    get_cache_root,
    get_legacy_cache_locations,
)
from notte_llm import tracer


class TestCacheRoot:
    """Tests for cache root directory creation and fallback."""

    def test_cache_root_in_home_directory(self):
        """Test that cache root is created in home directory when writable."""
        cache_root = get_cache_root()

        # Should be in home directory
        assert cache_root.exists()
        assert cache_root.is_dir()
        assert str(cache_root).startswith(str(Path.home()))
        assert ".notte" in str(cache_root)
        assert ".cache" in str(cache_root)

    def test_cache_root_is_writable(self):
        """Test that cache root directory is writable."""
        cache_root = get_cache_root()

        # Try writing a test file
        test_file = cache_root / "test_write.txt"
        _ = test_file.write_text("test")
        assert test_file.exists()
        assert test_file.read_text() == "test"

        # Clean up
        test_file.unlink()

    def test_cache_root_caching(self):
        """Test that cache root is cached after first call."""
        # Force recheck
        root1 = get_cache_root(force_recheck=True)
        root2 = get_cache_root()

        assert root1 == root2

    @patch.dict(os.environ, {"HOME": "/nonexistent/home"})
    @patch("notte_core.common.cache._is_writable")
    def test_cache_fallback_to_temp(self, mock_is_writable: Any) -> None:
        """Test fallback to temp directory when home is not writable."""

        # Mock home directory as not writable, temp as writable
        def mock_writable(path: Path) -> bool:
            return tempfile.gettempdir() in str(path)

        mock_is_writable.side_effect = mock_writable

        # Force recheck to trigger fallback logic
        cache_root = get_cache_root(force_recheck=True)

        # Should fall back to temp directory with consistent structure
        assert tempfile.gettempdir() in str(cache_root)
        assert ".notte" in str(cache_root)
        assert ".cache" in str(cache_root)


class TestSubdirectories:
    """Tests for cache subdirectory creation."""

    def test_ensure_telemetry_directory(self):
        """Test creation of telemetry subdirectory."""
        telemetry_dir = ensure_cache_directory(CacheDirectory.TELEMETRY)

        assert telemetry_dir.exists()
        assert telemetry_dir.is_dir()
        assert telemetry_dir.name == "telemetry"

    def test_ensure_traces_directory(self):
        """Test creation of traces subdirectory."""
        traces_dir = ensure_cache_directory(CacheDirectory.TRACES)

        assert traces_dir.exists()
        assert traces_dir.is_dir()
        assert traces_dir.name == "traces"

    def test_ensure_profiling_directory(self):
        """Test creation of profiling subdirectory."""
        profiling_dir = ensure_cache_directory(CacheDirectory.PROFILING)

        assert profiling_dir.exists()
        assert profiling_dir.is_dir()
        assert profiling_dir.name == "profiling"

    def test_ensure_files_directory(self):
        """Test creation of files subdirectory."""
        files_dir = ensure_cache_directory(CacheDirectory.FILES)

        assert files_dir.exists()
        assert files_dir.is_dir()
        assert files_dir.name == "files"

    def test_ensure_custom_subdirectory(self):
        """Test creation of custom subdirectory."""
        custom_dir = ensure_cache_directory("custom_subdir")

        assert custom_dir.exists()
        assert custom_dir.is_dir()
        assert custom_dir.name == "custom_subdir"

    def test_ensure_root_directory_only(self):
        """Test getting root directory without subdirectory."""
        root_dir = ensure_cache_directory(None)

        assert root_dir.exists()
        assert root_dir.is_dir()
        assert ".cache" in str(root_dir)

    def test_subdirectories_are_writable(self):
        """Test that all subdirectories are writable."""
        for subdir in CacheDirectory:
            cache_dir = ensure_cache_directory(subdir)

            # Try writing a test file
            test_file = cache_dir / "test_write.txt"
            _ = test_file.write_text("test")
            assert test_file.exists()

            # Clean up
            test_file.unlink()


class TestEnvironmentVariables:
    """Tests for environment variable overrides."""

    def test_xdg_cache_home_override(self):
        """Test XDG_CACHE_HOME override for telemetry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"XDG_CACHE_HOME": tmpdir}):
                # Import telemetry module to trigger directory creation
                # Force reload to pick up new env var
                from notte_core.common import telemetry

                _ = importlib.reload(telemetry)

                # Check that telemetry uses XDG_CACHE_HOME
                assert tmpdir in str(telemetry.TELEMETRY_DIR)

    def test_notte_cache_dir_override(self):
        """Test NOTTE_CACHE_DIR override for file storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"NOTTE_CACHE_DIR": tmpdir}):
                # Import files module to trigger directory creation
                # Force reload to pick up new env var
                from notte_sdk.endpoints import files

                _ = importlib.reload(files)

                # Check that files uses NOTTE_CACHE_DIR
                assert tmpdir == str(files.NOTTE_CACHE_DIR)

    def test_notte_traces_dir_override(self):
        """Test NOTTE_TRACES_DIR override for tracing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"NOTTE_TRACES_DIR": tmpdir, "DISABLE_NOTTE_LLM_TRACING": "false"}):
                # Import tracer module to trigger directory creation
                # Force reload to pick up new env var
                _ = importlib.reload(tracer)

                # Check that tracer uses NOTTE_TRACES_DIR
                assert tmpdir == str(tracer.TRACES_DIR)


class TestCacheInfo:
    """Tests for cache information functions."""

    def test_get_cache_info(self):
        """Test getting cache information."""
        info = get_cache_info()

        assert "cache_root" in info
        assert "using_temp_fallback" in info
        assert "platform" in info
        assert isinstance(info["cache_root"], str)
        assert isinstance(info["using_temp_fallback"], bool)
        assert isinstance(info["platform"], str)

    def test_get_legacy_cache_locations(self):
        """Test getting legacy cache locations."""
        legacy_locations = get_legacy_cache_locations()

        assert "telemetry" in legacy_locations
        assert "files" in legacy_locations
        assert isinstance(legacy_locations["telemetry"], Path)
        assert isinstance(legacy_locations["files"], Path)

    def test_check_for_legacy_data(self):
        """Test checking for legacy data."""
        legacy_check = check_for_legacy_data()

        assert "telemetry" in legacy_check
        assert "files" in legacy_check
        assert isinstance(legacy_check["telemetry"], bool)
        assert isinstance(legacy_check["files"], bool)


class TestIntegration:
    """Integration tests for the cache system."""

    def test_telemetry_uses_cache(self):
        """Test that telemetry module uses centralized cache."""
        # Force module reload to pick up current cache state
        from notte_core.common import telemetry

        _ = importlib.reload(telemetry)

        # Check that telemetry files are under cache root or in XDG override
        # The path should contain .notte and .cache somewhere in it
        telemetry_path = str(telemetry.TELEMETRY_DIR)
        xdg_override = os.getenv("XDG_CACHE_HOME")

        assert ".notte" in telemetry_path or (xdg_override is not None and xdg_override in telemetry_path)
        assert ".cache" in telemetry_path or (xdg_override is not None and xdg_override in telemetry_path)

    def test_tracer_uses_cache(self):
        """Test that tracer module uses centralized cache."""
        # Force module reload to pick up current cache state
        _ = importlib.reload(tracer)

        # Only check if tracing is enabled and not overridden
        if os.getenv("DISABLE_NOTTE_LLM_TRACING", "false").lower() == "false" and not os.getenv("NOTTE_TRACES_DIR"):
            # Check that traces are under cache root
            traces_path = str(tracer.TRACES_DIR)
            assert ".notte" in traces_path
            assert ".cache" in traces_path

    def test_files_uses_cache(self):
        """Test that files module uses centralized cache."""
        # Force module reload to pick up current cache state
        from notte_sdk.endpoints import files

        _ = importlib.reload(files)

        # Only check if not overridden
        if not os.getenv("NOTTE_CACHE_DIR"):
            files_path = str(files.NOTTE_CACHE_DIR)
            assert ".notte" in files_path
            assert ".cache" in files_path

    def test_profiling_uses_cache(self):
        """Test that profiling module uses centralized cache for default outputs."""
        from notte_core.profiling import profiler

        if not profiler.enable:
            pytest.skip("Profiling not enabled")

        cache_root = get_cache_root()
        profiling_dir = ensure_cache_directory(CacheDirectory.PROFILING)

        # The profiling dir should be under cache root
        assert str(cache_root) in str(profiling_dir)

    def test_concurrent_cache_creation(self):
        """Test that concurrent cache directory creation doesn't fail."""
        import concurrent.futures

        def create_cache():
            return ensure_cache_directory(CacheDirectory.TELEMETRY)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_cache) for _ in range(10)]
            results = [f.result() for f in futures]

        # All should return the same directory
        assert len(set(results)) == 1
        assert results[0].exists()


class TestPermissions:
    """Tests for cache directory permissions."""

    def test_cache_directories_have_correct_permissions(self):
        """Test that cache directories are created with appropriate permissions."""
        cache_root = get_cache_root()

        # Root should be readable and writable
        assert os.access(cache_root, os.R_OK)
        assert os.access(cache_root, os.W_OK)
        assert os.access(cache_root, os.X_OK)

        # Subdirectories should also be accessible
        for subdir in CacheDirectory:
            cache_dir = ensure_cache_directory(subdir)
            assert os.access(cache_dir, os.R_OK)
            assert os.access(cache_dir, os.W_OK)
            assert os.access(cache_dir, os.X_OK)
