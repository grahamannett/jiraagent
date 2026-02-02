"""Tests for audit hook."""

import json
from pathlib import Path

import pytest

from jira_agent.hooks.audit import AuditEntry, AuditLogger, make_audit_hook


class TestAuditEntry:
    """Tests for AuditEntry dataclass."""

    def test_basic_entry(self):
        """Create a basic audit entry."""
        entry = AuditEntry(
            timestamp="2024-01-01T00:00:00Z",
            tool_name="Read",
            tool_use_id="abc123",
            arguments={"file_path": "/test/file.py"},
        )

        assert entry.tool_name == "Read"
        assert entry.arguments == {"file_path": "/test/file.py"}
        assert entry.duration_ms is None

    def test_to_json(self):
        """Convert entry to JSON."""
        entry = AuditEntry(
            timestamp="2024-01-01T00:00:00Z",
            tool_name="Read",
            tool_use_id="abc123",
            arguments={"file_path": "/test/file.py"},
            duration_ms=42,
        )

        json_str = entry.to_json()
        data = json.loads(json_str)

        assert data["tool_name"] == "Read"
        assert data["duration_ms"] == 42
        assert data["arguments"]["file_path"] == "/test/file.py"


class TestAuditLogger:
    """Tests for AuditLogger class."""

    def test_log_tool_start(self, tmp_path):
        """Log a tool call start."""
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(output_path=log_file)

        logger.log_tool_start("Read", "id1", {"file_path": "/test/file.py"})

        entries = logger.get_entries()
        assert len(entries) == 1
        assert entries[0].tool_name == "Read"
        assert entries[0].tool_use_id == "id1"

        logger.close()

        # Verify file was written
        content = log_file.read_text()
        assert "Read" in content
        assert "file.py" in content

    def test_log_tool_end_calculates_duration(self, tmp_path):
        """Log tool end calculates duration."""
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(output_path=log_file)

        logger.log_tool_start("Read", "id1", {"file_path": "/test"})
        logger.log_tool_end("id1")

        entries = logger.get_entries()
        assert len(entries) == 1
        # Duration should be set (may be 0 for very fast)
        assert entries[0].duration_ms is not None
        assert entries[0].duration_ms >= 0

        logger.close()

    def test_multiple_tool_calls(self, tmp_path):
        """Log multiple tool calls."""
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(output_path=log_file)

        logger.log_tool_start("Read", "id1", {"file_path": "/a"})
        logger.log_tool_start("Write", "id2", {"file_path": "/b", "content": "x"})
        logger.log_tool_end("id1")
        logger.log_tool_end("id2")

        entries = logger.get_entries()
        assert len(entries) == 2
        assert entries[0].tool_name == "Read"
        assert entries[1].tool_name == "Write"

        logger.close()

    def test_sanitize_sensitive_fields(self, tmp_path):
        """Sensitive fields are redacted."""
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(output_path=log_file)

        logger.log_tool_start(
            "Bash",
            "id1",
            {
                "command": "echo hello",
                "api_token": "secret123",
                "password": "secret456",
            },
        )

        entries = logger.get_entries()
        assert entries[0].arguments["command"] == "echo hello"
        assert entries[0].arguments["api_token"] == "[REDACTED]"
        assert entries[0].arguments["password"] == "[REDACTED]"

        logger.close()

    def test_truncate_long_values(self, tmp_path):
        """Long values are truncated."""
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(output_path=log_file)

        long_content = "x" * 500
        logger.log_tool_start("Write", "id1", {"content": long_content})

        entries = logger.get_entries()
        assert len(entries[0].arguments["content"]) <= 203  # 200 + "..."

        logger.close()

    def test_text_format(self, tmp_path, capsys):
        """Test text format output."""
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(output_path=log_file, format="text")

        logger.log_tool_start("Read", "id1", {"file_path": "/test"})

        logger.close()

        content = log_file.read_text()
        # Text format should have tool name and args visible
        assert "Read" in content
        assert "file_path" in content

    def test_stderr_output(self, tmp_path, capsys):
        """Test stderr output."""
        logger = AuditLogger(stderr=True)

        logger.log_tool_start("Read", "id1", {"file_path": "/test"})

        logger.close()

        captured = capsys.readouterr()
        assert "[AUDIT]" in captured.err
        assert "Read" in captured.err

    def test_no_file_when_path_none(self):
        """No file operations when path is None."""
        logger = AuditLogger(output_path=None, stderr=False)

        logger.log_tool_start("Read", "id1", {"file_path": "/test"})
        logger.close()

        # Should not raise, just silently not write to file
        entries = logger.get_entries()
        assert len(entries) == 1

    def test_creates_parent_directories(self, tmp_path):
        """Creates parent directories if needed."""
        log_file = tmp_path / "nested" / "dir" / "audit.log"
        logger = AuditLogger(output_path=log_file)

        logger.log_tool_start("Read", "id1", {"file_path": "/test"})
        logger.close()

        assert log_file.exists()


class TestMakeAuditHook:
    """Tests for make_audit_hook factory."""

    @pytest.mark.asyncio
    async def test_hook_logs_tool_call(self, tmp_path):
        """Hook logs tool calls."""
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(output_path=log_file)
        hook = make_audit_hook(logger)

        input_data = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/test/file.py"},
        }

        result = await hook(input_data, "tool_id_123", None)

        # Hook should return empty dict (no modifications)
        assert result == {}

        # Logger should have the entry
        entries = logger.get_entries()
        assert len(entries) == 1
        assert entries[0].tool_name == "Read"
        assert entries[0].tool_use_id == "tool_id_123"

        logger.close()

    @pytest.mark.asyncio
    async def test_hook_handles_missing_tool_name(self, tmp_path):
        """Hook handles missing tool_name gracefully."""
        log_file = tmp_path / "audit.log"
        logger = AuditLogger(output_path=log_file)
        hook = make_audit_hook(logger)

        input_data = {"tool_input": {"file_path": "/test"}}

        result = await hook(input_data, "id1", None)

        assert result == {}
        entries = logger.get_entries()
        assert entries[0].tool_name == "unknown"

        logger.close()


class TestCLIAuditArgs:
    """Tests for CLI audit arguments."""

    def test_audit_log_defaults_none(self):
        """--audit-log defaults to None."""
        import tyro

        from jira_agent.cli import Args, RunArgs

        args = tyro.cli(Args, args=["run", "SPE-123"])

        assert isinstance(args, RunArgs)
        assert args.audit_log is None

    def test_audit_log_accepts_path(self):
        """--audit-log accepts a path."""
        import tyro

        from jira_agent.cli import Args, RunArgs

        args = tyro.cli(Args, args=["run", "SPE-123", "--audit-log", "/tmp/audit.log"])

        assert isinstance(args, RunArgs)
        assert args.audit_log == Path("/tmp/audit.log")

    def test_audit_stderr_defaults_false(self):
        """--audit-stderr defaults to False."""
        import tyro

        from jira_agent.cli import Args, RunArgs

        args = tyro.cli(Args, args=["run", "SPE-123"])

        assert isinstance(args, RunArgs)
        assert args.audit_stderr is False

    def test_audit_stderr_flag(self):
        """--audit-stderr flag works."""
        import tyro

        from jira_agent.cli import Args, RunArgs

        args = tyro.cli(Args, args=["run", "SPE-123", "--audit-stderr"])

        assert isinstance(args, RunArgs)
        assert args.audit_stderr is True
