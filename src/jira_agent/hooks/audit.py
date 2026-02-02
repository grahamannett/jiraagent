"""Audit hook for logging tool calls.

Logs all tool calls with timestamps, arguments, and duration for
debugging and understanding agent behavior.
"""

import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


@dataclass
class AuditEntry:
    """A single audit log entry."""

    timestamp: str
    tool_name: str
    tool_use_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    duration_ms: int | None = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(asdict(self), default=str)


class AuditLogger:
    """Logs tool calls to a file and/or stderr.

    Usage:
        logger = AuditLogger(output_path=Path("audit.log"))
        hook = logger.make_hook()
        # Use hook in agent configuration
    """

    def __init__(
        self,
        output_path: Path | None = None,
        stderr: bool = False,
        format: str = "json",  # noqa: A002
    ):
        """Initialize the audit logger.

        Args:
            output_path: Path to write audit log. If None, file logging is disabled.
            stderr: Whether to also log to stderr.
            format: Output format ("json" or "text").
        """
        self.output_path = output_path
        self.stderr = stderr
        self.format = format
        self._file: TextIO | None = None
        self._entries: list[AuditEntry] = []
        self._pending_calls: dict[str, datetime] = {}

    def _open_file(self) -> None:
        """Open the output file if configured."""
        if self.output_path and self._file is None:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self.output_path, "a")  # noqa: SIM115

    def _write_entry(self, entry: AuditEntry) -> None:
        """Write an entry to configured outputs."""
        if self.format == "json":
            line = entry.to_json()
        else:
            # Text format
            args_str = ", ".join(f"{k}={v!r}" for k, v in entry.arguments.items())
            duration = f" ({entry.duration_ms}ms)" if entry.duration_ms is not None else ""
            line = f"[{entry.timestamp}] {entry.tool_name}({args_str}){duration}"

        if self._file:
            self._file.write(line + "\n")
            self._file.flush()

        if self.stderr:
            print(f"[AUDIT] {line}", file=sys.stderr)

    def log_tool_start(self, tool_name: str, tool_use_id: str, arguments: dict[str, Any]) -> None:
        """Log the start of a tool call.

        Args:
            tool_name: Name of the tool being called.
            tool_use_id: Unique ID for this tool use.
            arguments: Arguments passed to the tool.
        """
        self._open_file()
        self._pending_calls[tool_use_id] = datetime.now(timezone.utc)

        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            arguments=self._sanitize_arguments(arguments),
        )
        self._entries.append(entry)
        self._write_entry(entry)

    def log_tool_end(self, tool_use_id: str) -> None:
        """Log the end of a tool call and calculate duration.

        Args:
            tool_use_id: Unique ID for the tool use that completed.
        """
        if tool_use_id in self._pending_calls:
            start_time = self._pending_calls.pop(tool_use_id)
            duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Update the last entry with duration if it matches
            for entry in reversed(self._entries):
                if entry.tool_use_id == tool_use_id:
                    entry.duration_ms = duration
                    break

    def _sanitize_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Sanitize arguments for logging.

        Truncates long values and redacts sensitive fields.
        """
        sanitized = {}
        sensitive_keys = {"token", "password", "secret", "api_key", "auth"}

        for key, value in arguments.items():
            # Redact sensitive fields
            if any(s in key.lower() for s in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, str) and len(value) > 200:
                sanitized[key] = value[:200] + "..."
            else:
                sanitized[key] = value

        return sanitized

    def get_entries(self) -> list[AuditEntry]:
        """Get all logged entries."""
        return self._entries.copy()

    def close(self) -> None:
        """Close the output file if open."""
        if self._file:
            self._file.close()
            self._file = None


def make_audit_hook(logger: AuditLogger):
    """Create a PreToolUse hook for audit logging.

    Args:
        logger: The AuditLogger instance to use.

    Returns:
        An async hook function for use with claude_agent_sdk.
    """

    async def audit_hook(
        input_data: dict[str, Any], tool_use_id: str, _context: Any
    ) -> dict[str, Any]:
        """PreToolUse hook that logs tool calls."""
        tool_name = input_data.get("tool_name", "unknown")
        tool_input = input_data.get("tool_input", {})

        logger.log_tool_start(tool_name, tool_use_id, tool_input)

        # Return empty dict to not modify the tool call
        return {}

    return audit_hook
