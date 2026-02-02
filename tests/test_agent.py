"""Tests for agent.py pure functions."""

from pathlib import Path
from unittest.mock import patch

from jira_agent.agent import slugify_summary, make_file_change_logger


class TestSlugifySummary:
    """Tests for the slugify_summary utility function."""

    def test_basic_conversion(self):
        """Basic words become lowercase hyphenated."""
        assert slugify_summary("Hello World") == "hello-world"

    def test_special_characters_become_hyphens(self):
        """Non-alphanumeric characters are replaced with hyphens."""
        assert slugify_summary("Cost Code Descriptions not Populating") == "cost-code-descriptions-not-populating"

    def test_max_length_truncates_at_word_boundary(self):
        """Long summaries truncate at word boundaries, not mid-word."""
        result = slugify_summary("This is a very long summary that exceeds the limit", max_len=20)
        assert len(result) <= 20
        assert not result.endswith("-")

    def test_strips_leading_trailing_hyphens(self):
        """Leading and trailing hyphens are removed."""
        assert slugify_summary("---hello---") == "hello"

    def test_empty_string_returns_empty(self):
        """Empty input returns empty output."""
        assert slugify_summary("") == ""

    def test_only_special_chars_returns_empty(self):
        """Input with only special characters returns empty."""
        assert slugify_summary("!@#$%") == ""


class TestMakeFileChangeLogger:
    """Tests for the make_file_change_logger function."""

    async def test_returns_empty_dict(self):
        """Hook returns empty dict."""
        hook = make_file_change_logger(Path("/tmp/repo"))
        result = await hook({"tool_input": {"file_path": "/tmp/repo/src/main.py"}}, "", None)
        assert result == {}

    async def test_strips_worktree_prefix_from_output(self):
        """Worktree prefix is stripped from printed path."""
        with patch("jira_agent.agent.print") as mock_print:
            hook = make_file_change_logger(Path("/tmp/repo"))
            _ = await hook({"tool_input": {"file_path": "/tmp/repo/src/main.py"}}, "", None)
            mock_print.assert_called_once()
            printed = mock_print.call_args[0][0]
            assert "src/main.py" in printed
            assert "/tmp/repo" not in printed

    async def test_handles_missing_file_path(self):
        """No crash when file_path is missing."""
        hook = make_file_change_logger(Path("/tmp/repo"))
        result = await hook({"tool_input": {}}, "", None)
        assert result == {}
