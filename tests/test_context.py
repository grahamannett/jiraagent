"""Tests for context module functions."""

import tempfile
from pathlib import Path

import pytest

from jira_agent.context import (
    context_exists,
    get_context_path_for_repo,
    get_default_context_dir,
    load_context,
)
from jira_agent.context.generator import _build_metadata_header


class TestGetDefaultContextDir:
    """Tests for the get_default_context_dir function."""

    def test_returns_contexts_dir_by_default(self, monkeypatch):
        """Without env var, returns {project}/contexts/."""
        monkeypatch.delenv("JIRA_AGENT_CONTEXTS_DIR", raising=False)
        result = get_default_context_dir()
        assert result.name == "contexts"
        assert result.parent.name == "jiraagent"

    def test_respects_env_var(self, monkeypatch):
        """JIRA_AGENT_CONTEXTS_DIR env var overrides default."""
        monkeypatch.setenv("JIRA_AGENT_CONTEXTS_DIR", "/custom/path")
        result = get_default_context_dir()
        assert result == Path("/custom/path")

    def test_expands_tilde_in_env_var(self, monkeypatch):
        """Tilde in env var is expanded to home directory."""
        monkeypatch.setenv("JIRA_AGENT_CONTEXTS_DIR", "~/contexts")
        result = get_default_context_dir()
        assert "~" not in str(result)
        assert result.name == "contexts"


class TestGetContextPathForRepo:
    """Tests for the get_context_path_for_repo function."""

    def test_returns_repo_specific_path(self, monkeypatch):
        """Returns path under contexts/{repo_name}/AGENT.md."""
        monkeypatch.delenv("JIRA_AGENT_CONTEXTS_DIR", raising=False)
        repo = Path("/path/to/my-project")
        result = get_context_path_for_repo(repo)
        assert result.name == "AGENT.md"
        assert result.parent.name == "my-project"

    def test_uses_repo_name_not_full_path(self, monkeypatch):
        """Only the repo name is used, not the full path."""
        monkeypatch.delenv("JIRA_AGENT_CONTEXTS_DIR", raising=False)
        repo = Path("/very/deep/nested/path/to/my-repo")
        result = get_context_path_for_repo(repo)
        assert "my-repo" in str(result)
        assert result.parent.name == "my-repo"


class TestLoadContext:
    """Tests for the load_context function."""

    def test_loads_existing_file(self):
        """Successfully loads content from existing file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("# Test Content\nHello world")
            path = Path(f.name)

        try:
            content = load_context(path)
            assert "# Test Content" in content
            assert "Hello world" in content
        finally:
            path.unlink()

    def test_raises_for_missing_file(self):
        """Raises FileNotFoundError for non-existent file."""
        path = Path("/nonexistent/path/AGENT.md")
        with pytest.raises(FileNotFoundError) as exc_info:
            load_context(path)
        assert "Context file not found" in str(exc_info.value)
        assert "jira-agent context generate" in str(exc_info.value)


class TestContextExists:
    """Tests for the context_exists function."""

    def test_returns_true_for_existing_file(self):
        """Returns True when file exists."""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            path = Path(f.name)

        try:
            assert context_exists(path) is True
        finally:
            path.unlink()

    def test_returns_false_for_missing_file(self):
        """Returns False when file doesn't exist."""
        path = Path("/nonexistent/path/AGENT.md")
        assert context_exists(path) is False


class TestBuildMetadataHeader:
    """Tests for the metadata header generation."""

    def test_contains_generated_timestamp(self):
        """Header contains Generated: timestamp."""
        header = _build_metadata_header(Path("/repo"), deep=False, line_count=100)
        assert "Generated:" in header

    def test_contains_mode_basic(self):
        """Header contains Mode: basic for non-deep."""
        header = _build_metadata_header(Path("/repo"), deep=False, line_count=100)
        assert "Mode: basic" in header

    def test_contains_mode_deep(self):
        """Header contains Mode: deep for deep=True."""
        header = _build_metadata_header(Path("/repo"), deep=True, line_count=100)
        assert "Mode: deep" in header

    def test_contains_repository_path(self):
        """Header contains Repository: path."""
        header = _build_metadata_header(Path("/path/to/repo"), deep=False, line_count=100)
        assert "Repository: /path/to/repo" in header

    def test_contains_line_count(self):
        """Header contains Lines: count."""
        header = _build_metadata_header(Path("/repo"), deep=False, line_count=1500)
        assert "Lines: 1500" in header

    def test_is_html_comment(self):
        """Header is wrapped in HTML comment."""
        header = _build_metadata_header(Path("/repo"), deep=False, line_count=100)
        assert header.startswith("<!--")
        assert "-->" in header
