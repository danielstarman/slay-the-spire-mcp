"""Startup cleanup utilities for handling zombie processes."""

import logging
import socket
import subprocess
import sys

logger = logging.getLogger(__name__)


def is_port_in_use(host: str, port: int) -> bool:
    """Check if a port is currently in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def find_pid_using_port(port: int) -> int | None:
    """Find the PID of the process using the given port.

    Returns:
        PID if found, None otherwise
    """
    if sys.platform == "win32":
        return _find_pid_windows(port)
    else:
        return _find_pid_unix(port)


def _find_pid_windows(port: int) -> int | None:
    """Find PID on Windows using netstat."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    try:
                        return int(parts[-1])
                    except ValueError:
                        continue
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning(f"Failed to find PID using netstat: {e}")
    return None


def _find_pid_unix(port: int) -> int | None:
    """Find PID on Unix using lsof."""
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip():
            return int(result.stdout.strip().split()[0])
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError) as e:
        logger.warning(f"Failed to find PID using lsof: {e}")
    return None


def kill_process(pid: int) -> bool:
    """Kill a process by PID.

    Returns:
        True if killed successfully, False otherwise
    """
    if sys.platform == "win32":
        return _kill_process_windows(pid)
    else:
        return _kill_process_unix(pid)


def _kill_process_windows(pid: int) -> bool:
    """Kill process on Windows using taskkill."""
    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning(f"Failed to kill process {pid}: {e}")
        return False


def _kill_process_unix(pid: int) -> bool:
    """Kill process on Unix using kill."""
    import os
    import signal

    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except (ProcessLookupError, PermissionError) as e:
        logger.warning(f"Failed to kill process {pid}: {e}")
        return False


def cleanup_stale_port(host: str, port: int) -> bool:
    """Clean up a stale process holding a port.

    Args:
        host: The host address
        port: The port number

    Returns:
        True if port is now available, False otherwise
    """
    import os

    if not is_port_in_use(host, port):
        return True

    logger.info(f"Port {port} is in use, attempting cleanup...")

    pid = find_pid_using_port(port)
    if pid is None:
        logger.warning(f"Could not find PID for process on port {port}")
        return False

    # Don't kill our own process
    current_pid = os.getpid()
    if pid == current_pid:
        logger.warning(
            f"Port {port} is held by our own process (PID {pid}), cannot clean up"
        )
        return False

    logger.info(f"Found process {pid} on port {port}, terminating...")

    if kill_process(pid):
        # Give the OS a moment to release the port
        import time

        time.sleep(0.5)

        if not is_port_in_use(host, port):
            logger.info(f"Successfully cleaned up port {port}")
            return True
        else:
            logger.warning(f"Process killed but port {port} still in use")

    return False
