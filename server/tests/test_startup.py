"""Tests for startup cleanup utilities.

Tests the server's ability to:
- Detect if a port is in use
- Find the PID of a process using a port
- Clean up stale processes holding ports
"""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
from unittest import mock

import pytest

from slay_the_spire_mcp.startup import (
    cleanup_stale_port,
    find_pid_using_port,
    is_port_in_use,
    kill_process,
)


# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture
def free_port() -> int:
    """Get a free port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def bound_port() -> tuple[socket.socket, int]:
    """Create a socket bound to a port.

    Returns:
        Tuple of (socket, port) - caller is responsible for closing socket
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    return s, port


# ==============================================================================
# Happy Path Tests
# ==============================================================================


class TestIsPortInUse:
    """Tests for is_port_in_use function."""

    def test_is_port_in_use_when_free(self, free_port: int) -> None:
        """Given an unused port, is_port_in_use returns False."""
        assert is_port_in_use("127.0.0.1", free_port) is False

    def test_is_port_in_use_when_bound(
        self, bound_port: tuple[socket.socket, int]
    ) -> None:
        """Given a port with a listening socket, is_port_in_use returns True."""
        sock, port = bound_port
        try:
            assert is_port_in_use("127.0.0.1", port) is True
        finally:
            sock.close()


class TestCleanupStalePort:
    """Tests for cleanup_stale_port function."""

    def test_cleanup_stale_port_when_free(self, free_port: int) -> None:
        """Given an unused port, cleanup_stale_port returns True immediately."""
        result = cleanup_stale_port("127.0.0.1", free_port)
        assert result is True


class TestFindPidUsingPort:
    """Tests for find_pid_using_port function."""

    def test_find_pid_returns_none_for_free_port(self, free_port: int) -> None:
        """Given an unused port, find_pid_using_port returns None."""
        result = find_pid_using_port(free_port)
        assert result is None


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestCleanupEdgeCases:
    """Tests for edge cases in cleanup functionality."""

    def test_cleanup_handles_race_condition(self, free_port: int) -> None:
        """Given port freed by another process, cleanup succeeds."""
        # Port is already free, cleanup should return True immediately
        result = cleanup_stale_port("127.0.0.1", free_port)
        assert result is True

    def test_cleanup_handles_permission_denied(
        self, bound_port: tuple[socket.socket, int]
    ) -> None:
        """Given a process we can't kill, cleanup returns False gracefully."""
        sock, port = bound_port
        try:
            # Mock find_pid to return a valid PID (not our own)
            # Mock kill_process to fail (simulating permission denied)
            with (
                mock.patch(
                    "slay_the_spire_mcp.startup.find_pid_using_port", return_value=12345
                ),
                mock.patch(
                    "slay_the_spire_mcp.startup.kill_process", return_value=False
                ),
            ):
                result = cleanup_stale_port("127.0.0.1", port)
                assert result is False
        finally:
            sock.close()

    def test_cleanup_skips_own_process(
        self, bound_port: tuple[socket.socket, int], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Given port is held by our own process, cleanup skips kill and returns False."""
        import os

        sock, port = bound_port
        try:
            # Mock find_pid to return our own PID
            with mock.patch(
                "slay_the_spire_mcp.startup.find_pid_using_port",
                return_value=os.getpid(),
            ):
                with caplog.at_level(logging.WARNING):
                    result = cleanup_stale_port("127.0.0.1", port)
                    assert result is False
                    assert "our own process" in caplog.text
        finally:
            sock.close()


# ==============================================================================
# Error Condition Tests
# ==============================================================================


class TestErrorHandling:
    """Tests for error handling in startup utilities."""

    def test_find_pid_handles_netstat_failure(self) -> None:
        """Given netstat/lsof unavailable, returns None without crashing."""
        # Mock subprocess.run to raise FileNotFoundError (command not found)
        with mock.patch(
            "subprocess.run", side_effect=FileNotFoundError("netstat not found")
        ):
            result = find_pid_using_port(7777)
            assert result is None

    def test_find_pid_handles_timeout(self) -> None:
        """Given command timeout, returns None without crashing."""
        with mock.patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 10)
        ):
            result = find_pid_using_port(7777)
            assert result is None

    def test_kill_process_handles_invalid_pid(self) -> None:
        """Given an invalid PID, kill_process returns False."""
        # Use a PID that's almost certainly not running
        result = kill_process(999999999)
        assert result is False

    def test_cleanup_logs_warning_on_failure(
        self, bound_port: tuple[socket.socket, int], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Given cleanup failure, warning is logged."""
        sock, port = bound_port
        try:
            # Mock find_pid to return None (can't find process)
            with mock.patch(
                "slay_the_spire_mcp.startup.find_pid_using_port", return_value=None
            ):
                with caplog.at_level(logging.WARNING):
                    result = cleanup_stale_port("127.0.0.1", port)
                    assert result is False
                    assert "Could not find PID" in caplog.text
        finally:
            sock.close()


# ==============================================================================
# Platform-Specific Tests
# ==============================================================================


class TestPlatformSpecific:
    """Tests for platform-specific behavior."""

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
    def test_find_pid_uses_netstat_on_windows(self) -> None:
        """On Windows, find_pid_using_port uses netstat."""
        # Create a mock result that simulates netstat output
        mock_result = mock.MagicMock()
        mock_result.stdout = (
            "  TCP    127.0.0.1:7777    0.0.0.0:0    LISTENING    12345\n"
        )
        mock_result.returncode = 0

        with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
            result = find_pid_using_port(7777)
            assert result == 12345
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0] == ["netstat", "-ano"]

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    def test_find_pid_uses_lsof_on_unix(self) -> None:
        """On Unix, find_pid_using_port uses lsof."""
        mock_result = mock.MagicMock()
        mock_result.stdout = "12345\n"
        mock_result.returncode = 0

        with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
            result = find_pid_using_port(7777)
            assert result == 12345
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0] == ["lsof", "-i", ":7777", "-t"]

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
    def test_kill_process_uses_taskkill_on_windows(self) -> None:
        """On Windows, kill_process uses taskkill."""
        mock_result = mock.MagicMock()
        mock_result.returncode = 0

        with mock.patch("subprocess.run", return_value=mock_result) as mock_run:
            result = kill_process(12345)
            assert result is True
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0] == ["taskkill", "/PID", "12345", "/F"]

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-specific test")
    def test_kill_process_uses_signal_on_unix(self) -> None:
        """On Unix, kill_process uses os.kill with SIGTERM."""
        with mock.patch("os.kill") as mock_kill:
            result = kill_process(12345)
            assert result is True
            mock_kill.assert_called_once()
            import signal

            mock_kill.assert_called_with(12345, signal.SIGTERM)


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestIntegration:
    """Integration tests for the full cleanup flow."""

    def test_full_cleanup_flow_mocked(
        self, bound_port: tuple[socket.socket, int]
    ) -> None:
        """Test the full cleanup flow with mocked subprocess calls."""
        sock, port = bound_port
        try:
            # Mock the find_pid and kill_process to simulate successful cleanup
            with (
                mock.patch(
                    "slay_the_spire_mcp.startup.find_pid_using_port", return_value=12345
                ),
                mock.patch(
                    "slay_the_spire_mcp.startup.kill_process", return_value=True
                ),
                # Also mock is_port_in_use to return False after "killing"
                mock.patch(
                    "slay_the_spire_mcp.startup.is_port_in_use",
                    side_effect=[True, False],
                ),
            ):
                result = cleanup_stale_port("127.0.0.1", port)
                assert result is True
        finally:
            sock.close()

    def test_cleanup_when_kill_succeeds_but_port_still_bound(
        self, bound_port: tuple[socket.socket, int], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test when kill succeeds but port remains bound (e.g., TIME_WAIT)."""
        sock, port = bound_port
        try:
            with (
                mock.patch(
                    "slay_the_spire_mcp.startup.find_pid_using_port", return_value=12345
                ),
                mock.patch(
                    "slay_the_spire_mcp.startup.kill_process", return_value=True
                ),
                # Port still in use after killing
                mock.patch(
                    "slay_the_spire_mcp.startup.is_port_in_use", return_value=True
                ),
            ):
                with caplog.at_level(logging.WARNING):
                    result = cleanup_stale_port("127.0.0.1", port)
                    assert result is False
                    assert "still in use" in caplog.text
        finally:
            sock.close()
