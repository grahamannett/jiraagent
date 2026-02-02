"""Tests for the summary module."""

from pathlib import Path

import pytest

from jira_agent.agent import AgentResult
from jira_agent.integrations import Ticket
from jira_agent.summary import (
    SummaryContext,
    SummaryOptions,
    _get_output_path,
    _version_existing_summary,
    generate_summary,
    write_summary,
)


@pytest.fixture
def sample_ticket() -> Ticket:
    """Create a sample ticket for testing."""
    return Ticket(
        key="PROJ-123",
        summary="Add payment due date to statements",
        description="Implement payment due date field",
        issue_type="Story",
        priority="High",
        status="In Progress",
    )


@pytest.fixture
def sample_result() -> AgentResult:
    """Create a sample agent result for testing."""
    return AgentResult(
        success=True,
        summary="Added dueDate field to backend entity, GraphQL schema, and frontend.",
        files=[
            "/path/to/worktree/src/api/statement.py",
            "/path/to/worktree/src/frontend/StatementTable.tsx",
        ],
        verification_status="complete",
        remaining_work=[],
    )


@pytest.fixture
def sample_context(
    sample_ticket: Ticket, sample_result: AgentResult, tmp_path: Path
) -> SummaryContext:
    """Create a sample summary context for testing."""
    return SummaryContext(
        ticket=sample_ticket,
        result=sample_result,
        worktree_path=tmp_path / "worktree",
        branch_name="PROJ-123-add-payment-due-date",
        duration_seconds=685,
        context_file=Path("contexts/myrepo/AGENT.md"),
        jira_url="https://company.atlassian.net",
    )


class TestGenerateSummary:
    """Tests for generate_summary function."""

    def test_basic_summary(self, sample_context: SummaryContext) -> None:
        """Test basic summary generation without metadata."""
        options = SummaryOptions()
        summary = generate_summary(sample_context, options)

        assert "# Agent Summary: PROJ-123" in summary
        assert "**PROJ-123**: Add payment due date to statements" in summary
        assert "Added dueDate field" in summary
        assert "## Files Changed (2)" in summary
        assert "## Status" in summary
        assert "## Remaining Work" in summary
        assert "(none)" in summary  # No remaining work

    def test_summary_with_remaining_work(
        self, sample_ticket: Ticket, tmp_path: Path
    ) -> None:
        """Test summary with remaining work items."""
        result = AgentResult(
            success=True,
            summary="Partial implementation",
            files=["/path/file.py"],
            verification_status="partial",
            remaining_work=["Add unit tests", "Update documentation"],
        )
        ctx = SummaryContext(
            ticket=sample_ticket,
            result=result,
            worktree_path=tmp_path,
            branch_name=None,
            duration_seconds=100,
            context_file=Path("contexts/repo/AGENT.md"),
            jira_url="https://jira.example.com",
        )
        options = SummaryOptions()
        summary = generate_summary(ctx, options)

        assert "- Add unit tests" in summary
        assert "- Update documentation" in summary

    def test_summary_with_metadata(self, sample_context: SummaryContext) -> None:
        """Test summary generation with metadata included."""
        options = SummaryOptions(include_metadata=True)
        summary = generate_summary(sample_context, options)

        assert "## Metadata" in summary
        assert "**Generated**:" in summary
        assert "**Duration**: 685s" in summary
        assert "**Branch**: PROJ-123-add-payment-due-date" in summary
        assert "**Ticket Type**: Story" in summary
        assert "**Ticket Priority**: High" in summary
        assert "https://company.atlassian.net/browse/PROJ-123" in summary

    def test_summary_without_branch(
        self, sample_ticket: Ticket, sample_result: AgentResult, tmp_path: Path
    ) -> None:
        """Test summary when no branch name is provided."""
        ctx = SummaryContext(
            ticket=sample_ticket,
            result=sample_result,
            worktree_path=tmp_path,
            branch_name=None,
            duration_seconds=100,
            context_file=Path("contexts/repo/AGENT.md"),
            jira_url="https://jira.example.com",
        )
        options = SummaryOptions(include_metadata=True)
        summary = generate_summary(ctx, options)

        # Should not have branch line
        assert "**Branch**:" not in summary

    def test_summary_failed_result(self, sample_ticket: Ticket, tmp_path: Path) -> None:
        """Test summary for failed agent result."""
        result = AgentResult(
            success=False,
            summary="Agent failed: Could not parse schema",
            files=["/path/partial.py"],
        )
        ctx = SummaryContext(
            ticket=sample_ticket,
            result=result,
            worktree_path=tmp_path,
            branch_name=None,
            duration_seconds=50,
            context_file=Path("contexts/repo/AGENT.md"),
            jira_url="https://jira.example.com",
        )
        options = SummaryOptions()
        summary = generate_summary(ctx, options)

        assert "Failed" in summary
        assert "Could not parse schema" in summary

    def test_summary_relative_paths(
        self, sample_ticket: Ticket, tmp_path: Path
    ) -> None:
        """Test that file paths are made relative to worktree."""
        worktree = tmp_path / "myworktree"
        result = AgentResult(
            success=True,
            summary="Done",
            files=[
                str(worktree / "src/api/file.py"),
                str(worktree / "tests/test_file.py"),
            ],
        )
        ctx = SummaryContext(
            ticket=sample_ticket,
            result=result,
            worktree_path=worktree,
            branch_name=None,
            duration_seconds=100,
            context_file=Path("contexts/repo/AGENT.md"),
            jira_url="https://jira.example.com",
        )
        options = SummaryOptions()
        summary = generate_summary(ctx, options)

        assert "- src/api/file.py" in summary
        assert "- tests/test_file.py" in summary
        assert str(worktree) not in summary


class TestVersionExistingSummary:
    """Tests for _version_existing_summary function."""

    def test_no_existing_file(self, tmp_path: Path) -> None:
        """Test versioning when file doesn't exist."""
        summary_path = tmp_path / "AGENT_SUMMARY.md"
        # Should not raise
        _version_existing_summary(summary_path)
        assert not summary_path.exists()

    def test_version_first_existing(self, tmp_path: Path) -> None:
        """Test versioning first existing file."""
        summary_path = tmp_path / "AGENT_SUMMARY.md"
        summary_path.write_text("Original content")

        _version_existing_summary(summary_path)

        assert not summary_path.exists()
        versioned = tmp_path / "AGENT_SUMMARY.1.md"
        assert versioned.exists()
        assert versioned.read_text() == "Original content"

    def test_version_multiple_existing(self, tmp_path: Path) -> None:
        """Test versioning with multiple existing versions."""
        summary_path = tmp_path / "AGENT_SUMMARY.md"
        summary_path.write_text("Current")
        (tmp_path / "AGENT_SUMMARY.1.md").write_text("Version 1")
        (tmp_path / "AGENT_SUMMARY.2.md").write_text("Version 2")

        _version_existing_summary(summary_path)

        assert not summary_path.exists()
        assert (tmp_path / "AGENT_SUMMARY.3.md").exists()
        assert (tmp_path / "AGENT_SUMMARY.3.md").read_text() == "Current"


class TestGetOutputPath:
    """Tests for _get_output_path function."""

    def test_explicit_path(self, sample_context: SummaryContext) -> None:
        """Test with explicit output path."""
        explicit = Path("/custom/path/summary.md")
        options = SummaryOptions(output_path=explicit)

        result = _get_output_path(sample_context, options)

        assert result == explicit

    def test_default_worktree_root(self, sample_context: SummaryContext) -> None:
        """Test default output to worktree root."""
        options = SummaryOptions()

        result = _get_output_path(sample_context, options)

        expected = sample_context.worktree_path / "AGENT_SUMMARY.md"
        assert result == expected

    def test_to_contexts_directory(
        self, sample_context: SummaryContext, tmp_path: Path
    ) -> None:
        """Test output to contexts directory."""
        options = SummaryOptions(to_contexts=True)
        contexts_dir = tmp_path / "contexts"

        result = _get_output_path(sample_context, options, contexts_dir)

        # worktree_path.name is "worktree" from fixture
        expected = contexts_dir / "worktree" / "PROJ-123" / "AGENT_SUMMARY.md"
        assert result == expected


class TestWriteSummary:
    """Tests for write_summary function."""

    def test_write_to_default_location(
        self, sample_context: SummaryContext, tmp_path: Path
    ) -> None:
        """Test writing summary to default worktree location."""
        # Update context to use tmp_path
        sample_context.worktree_path = tmp_path
        options = SummaryOptions()

        result = write_summary(sample_context, options)

        assert result == tmp_path / "AGENT_SUMMARY.md"
        assert result.exists()
        content = result.read_text()
        assert "PROJ-123" in content

    def test_write_to_contexts_with_versioning(
        self, sample_context: SummaryContext, tmp_path: Path
    ) -> None:
        """Test writing to contexts directory with versioning."""
        sample_context.worktree_path = tmp_path / "myrepo"
        contexts_dir = tmp_path / "contexts"
        options = SummaryOptions(to_contexts=True)

        # Write first summary
        path1 = write_summary(sample_context, options, contexts_dir)
        assert path1.exists()

        # Write second summary - should version the first
        path2 = write_summary(sample_context, options, contexts_dir)

        assert path2.exists()
        assert (path2.parent / "AGENT_SUMMARY.1.md").exists()

    def test_write_to_custom_path(
        self, sample_context: SummaryContext, tmp_path: Path
    ) -> None:
        """Test writing to custom filepath."""
        custom_path = tmp_path / "custom" / "MY_SUMMARY.md"
        options = SummaryOptions(output_path=custom_path)

        result = write_summary(sample_context, options)

        assert result == custom_path
        assert result.exists()

    def test_write_creates_parent_directories(
        self, sample_context: SummaryContext, tmp_path: Path
    ) -> None:
        """Test that parent directories are created."""
        deep_path = tmp_path / "a" / "b" / "c" / "summary.md"
        options = SummaryOptions(output_path=deep_path)

        result = write_summary(sample_context, options)

        assert result == deep_path
        assert result.exists()
