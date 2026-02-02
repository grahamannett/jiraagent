"""Simple logging abstraction for jira-agent.

This module provides a thin wrapper around Python's logging module that:
- Works like print() by default (stdout, human-readable)
- Can easily add file logging or other handlers
- Supports log levels for filtering output
- Uses no external dependencies

Two output mechanisms:
1. `print()` - Drop-in replacement, redirectable to files
2. `log.*()` - Structured logging with levels, for debugging/errors

Usage:
    from jira_agent.log import print, log

    # User-facing output (drop-in replacement for builtin print)
    print("🎫 Processing ticket SPE-2701")
    print(f"✅ Done: {result.summary}")
    print("=" * 60)

    # To fall back to builtin print, just comment out the import above

    # Structured logging (with level prefixes)
    log.info("Connecting to Jira API")
    log.debug("Request payload: ...")
    log.error("Connection failed")
    log.exception("Unexpected error")  # Includes stack trace

    # Configuration
    log.set_level("DEBUG")
    log.add_file_handler("/var/log/jira-agent.log")
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import IO, ClassVar, override


def _fmt_record(record: logging.LogRecord, format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format the timestamp of a log record.

    Args:
        record: The LogRecord whose timestamp to format.
        format: The datetime format string (default: "%Y-%m-%d %H:%M:%S").

    Returns:
        The formatted timestamp as a string.
    """
    return datetime.fromtimestamp(record.created).strftime(format)


class AgentLogger:
    """Centralized logger for jira-agent.

    Wraps Python's logging module with a simpler API and sensible defaults.
    """

    # Log level mapping
    LEVELS: ClassVar[dict[str, int]] = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    _logger: logging.Logger

    def __init__(self, name: str = "jira-agent"):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)  # Allow all levels, filter at handler

        # Prevent duplicate handlers if module is reloaded
        if not self._logger.handlers:
            self._add_console_handler()

    def _add_console_handler(self) -> None:
        """Add default console handler with human-readable format."""
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)  # Default to INFO for console
        handler.setFormatter(AgentFormatter())
        self._logger.addHandler(handler)

    def set_level(self, level: str | int) -> None:
        """Set the minimum log level for console output.

        Args:
            level: "DEBUG", "INFO", "WARN", "ERROR" or logging constant
        """
        if isinstance(level, str):
            level = self.LEVELS.get(level.upper(), logging.INFO)

        # Update console handler level
        for handler in self._logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setLevel(level)

    def add_file_handler(
        self,
        path: str | Path,
        level: str | int = "DEBUG",
        max_bytes: int = 10_000_000,  # 10MB
        backup_count: int = 3,
    ) -> None:
        """Add a rotating file handler.

        Args:
            path: File path for logs
            level: Minimum level for file output
            max_bytes: Max file size before rotation
            backup_count: Number of backup files to keep
        """
        from logging.handlers import RotatingFileHandler

        if isinstance(level, str):
            level = self.LEVELS.get(level.upper(), logging.DEBUG)

        handler = RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        handler.setLevel(level)
        handler.setFormatter(AgentFormatter(include_timestamp=True))
        self._logger.addHandler(handler)

    def add_handler(self, handler: logging.Handler) -> None:
        """Add a custom handler (e.g., for AWS CloudWatch).

        Args:
            handler: Any logging.Handler subclass
        """
        self._logger.addHandler(handler)

    def debug(self, msg: str) -> None:
        """Log debug message (verbose, for troubleshooting)."""
        self._logger.debug(msg)

    def info(self, msg: str) -> None:
        """Log info message (normal operation)."""
        self._logger.info(msg)

    def warn(self, msg: str) -> None:
        """Log warning message (unexpected but recoverable)."""
        self._logger.warning(msg)

    def error(self, msg: str) -> None:
        """Log error message (failure)."""
        self._logger.error(msg)

    def critical(self, msg: str) -> None:
        """Log critical message (system failure)."""
        self._logger.critical(msg)

    def exception(self, msg: str) -> None:
        """Log error with exception traceback."""
        self._logger.exception(msg)


class AgentFormatter(logging.Formatter):
    """Custom formatter with optional colors and clean output.

    Console output is minimal and human-readable.
    File output includes timestamps and more detail.
    """

    # ANSI color codes (only used if terminal supports it)
    COLORS: ClassVar[dict[int, str]] = {
        logging.DEBUG: "\033[36m",  # Cyan
        logging.INFO: "\033[32m",  # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",  # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET: ClassVar[str] = "\033[0m"

    include_timestamp: bool
    use_colors: bool

    def __init__(self, include_timestamp: bool = False, use_colors: bool | None = None):
        """Initialize formatter.

        Args:
            include_timestamp: Include ISO timestamp (for file logs)
            use_colors: Force colors on/off, or None for auto-detect
        """
        super().__init__()
        self.include_timestamp = include_timestamp
        self.use_colors = use_colors if use_colors is not None else sys.stdout.isatty()

    @override
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record."""
        parts: list[str] = []

        # Timestamp for file logs
        if self.include_timestamp:
            parts.append(f"[{_fmt_record(record)}]")

        # Level indicator
        level_char = record.levelname[0]  # D, I, W, E, C
        if self.use_colors:
            color = self.COLORS.get(record.levelno, "")
            parts.append(f"{color}[{level_char}]{self.RESET}")
        else:
            parts.append(f"[{level_char}]")

        # The actual message
        parts.append(record.getMessage())

        return " ".join(parts)


# Global logger instance
log = AgentLogger()


class OutputWriter:
    """Clean output writer for user-facing messages.

    Like print() but can be redirected to files alongside the logger.
    No prefixes, no levels - just clean output.
    """

    _streams: list[IO[str]]

    def __init__(self) -> None:
        self._streams = [sys.stdout]

    def add_file(self, path: str | Path) -> None:
        """Add a file to write output to (in addition to stdout)."""
        self._streams.append(open(path, "a"))  # noqa: SIM115

    def write(self, *args: object, sep: str = " ", end: str = "\n") -> None:
        """Write output to all streams (like print)."""
        message = sep.join(str(arg) for arg in args) + end
        for stream in self._streams:
            _ = stream.write(message)
            stream.flush()

    def __call__(self, *args: object, sep: str = " ", end: str = "\n") -> None:
        """Allow calling instance directly: out("message")."""
        self.write(*args, sep=sep, end=end)


# Global output writer instance
_output = OutputWriter()


def print(*args: object, sep: str = " ", end: str = "\n") -> None:  # noqa: A001
    """Drop-in replacement for print() that can be redirected.

    Works exactly like builtin print() but goes through the output system
    so it can be redirected to files when running on remote machines.

    Usage:
        from jira_agent.log import print

        print("🎫 Processing ticket SPE-2701")
        print(f"✅ Done: {result.summary}")

    To fall back to builtin print, just comment out the import.

    To also write to a file:
        from jira_agent.log import _output
        _output.add_file("/var/log/jira-agent-output.log")
    """
    _output.write(*args, sep=sep, end=end)
