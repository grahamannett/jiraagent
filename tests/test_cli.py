"""Tests for CLI argument parsing with tyro."""

from pathlib import Path

import pytest
import tyro

from jira_agent.cli import (
    Args,
    CleanupArgs,
    ContextGenerateArgs,
    ContextPathArgs,
    ContextShowArgs,
    HealthArgs,
    RunArgs,
    TicketArgs,
)


class TestRunCommand:
    """Tests for the 'run' command argument parsing."""

    def test_requires_ticket_key(self):
        """Run command requires a ticket key."""
        with pytest.raises(SystemExit):
            tyro.cli(Args, args=["run"])

    def test_parses_ticket_key(self):
        """Ticket key is parsed as positional argument."""
        args = tyro.cli(Args, args=["run", "SPE-123"])

        assert isinstance(args, RunArgs)
        assert args.ticket == "SPE-123"

    @pytest.mark.parametrize(
        ("cli_args", "expected_attr", "expected_value"),
        [
            (["run", "SPE-123", "--dry-run"], "dry_run", True),
            (["run", "SPE-123", "--no-pr"], "no_pr", True),
            (["run", "SPE-123"], "dry_run", False),
            (["run", "SPE-123"], "no_pr", False),
        ],
        ids=["dry-run-flag", "no-pr-flag", "no-dry-run", "no-no-pr"],
    )
    def test_boolean_flags(self, cli_args, expected_attr, expected_value):
        """Boolean flags are parsed correctly."""
        args = tyro.cli(Args, args=cli_args)

        assert isinstance(args, RunArgs)
        assert getattr(args, expected_attr) == expected_value

    @pytest.mark.parametrize(
        ("cli_args", "expected_branch"),
        [
            (["run", "SPE-123"], None),  # No --branch flag
            (["run", "SPE-123", "--branch", "my-branch"], "my-branch"),  # --branch with value
        ],
        ids=["no-branch", "branch-with-value"],
    )
    def test_branch_argument(self, cli_args, expected_branch):
        """--branch flag handles values correctly."""
        args = tyro.cli(Args, args=cli_args)

        assert isinstance(args, RunArgs)
        assert args.branch == expected_branch

    def test_context_path_converted_to_path(self):
        """--context value is converted to Path."""
        args = tyro.cli(Args, args=["run", "SPE-123", "--context", "/path/to/AGENT.md"])

        assert isinstance(args, RunArgs)
        assert args.context == Path("/path/to/AGENT.md")
        assert isinstance(args.context, Path)

    def test_base_commit_parsed(self):
        """--base-commit captures the commit SHA."""
        args = tyro.cli(Args, args=["run", "SPE-123", "--base-commit", "abc123f"])

        assert isinstance(args, RunArgs)
        assert args.base_commit == "abc123f"

    def test_all_options_together(self):
        """All options can be combined."""
        args = tyro.cli(
            Args,
            args=[
                "run",
                "SPE-123",
                "--dry-run",
                "--no-pr",
                "--branch",
                "feature-branch",
                "--context",
                "/custom/AGENT.md",
                "--base-commit",
                "abc123f",
            ],
        )

        assert isinstance(args, RunArgs)
        assert args.ticket == "SPE-123"
        assert args.dry_run is True
        assert args.no_pr is True
        assert args.branch == "feature-branch"
        assert args.context == Path("/custom/AGENT.md")
        assert args.base_commit == "abc123f"

    @pytest.mark.parametrize(
        ("cli_args", "expected_verify", "expected_url"),
        [
            (["run", "SPE-123"], False, "http://localhost:3000"),  # Default values
            (["run", "SPE-123", "--verify"], True, "http://localhost:3000"),  # --verify flag
            (
                ["run", "SPE-123", "--verify-url", "http://localhost:8080"],
                False,
                "http://localhost:8080",
            ),  # Custom URL
            (
                ["run", "SPE-123", "--verify", "--verify-url", "http://staging.example.com"],
                True,
                "http://staging.example.com",
            ),  # Both
        ],
        ids=["defaults", "verify-flag", "custom-url", "verify-with-custom-url"],
    )
    def test_verify_arguments(self, cli_args, expected_verify, expected_url):
        """--verify and --verify-url flags are parsed correctly."""
        args = tyro.cli(Args, args=cli_args)

        assert isinstance(args, RunArgs)
        assert args.verify == expected_verify
        assert args.verify_url == expected_url

    @pytest.mark.parametrize(
        ("cli_args", "expected_summary", "expected_metadata", "expected_to_contexts"),
        [
            (["run", "SPE-123"], False, False, False),  # Defaults
            (["run", "SPE-123", "--summary"], True, False, False),  # Summary only
            (["run", "SPE-123", "--summary-metadata"], False, True, False),  # Metadata only
            (["run", "SPE-123", "--summary-to-contexts"], False, False, True),  # To contexts
            (
                ["run", "SPE-123", "--summary", "--summary-metadata", "--summary-to-contexts"],
                True,
                True,
                True,
            ),  # All flags
        ],
        ids=["defaults", "summary-only", "metadata-only", "to-contexts-only", "all-summary-flags"],
    )
    def test_summary_arguments(
        self, cli_args, expected_summary, expected_metadata, expected_to_contexts
    ):
        """--summary flags are parsed correctly."""
        args = tyro.cli(Args, args=cli_args)

        assert isinstance(args, RunArgs)
        assert args.summary == expected_summary
        assert args.summary_metadata == expected_metadata
        assert args.summary_to_contexts == expected_to_contexts

    def test_summary_filepath_argument(self):
        """--summary-filepath is parsed correctly."""
        args = tyro.cli(
            Args, args=["run", "SPE-123", "--summary-filepath", "/custom/path/summary.md"]
        )

        assert isinstance(args, RunArgs)
        assert args.summary_filepath == Path("/custom/path/summary.md")

    def test_summary_filepath_defaults_none(self):
        """--summary-filepath defaults to None."""
        args = tyro.cli(Args, args=["run", "SPE-123"])

        assert isinstance(args, RunArgs)
        assert args.summary_filepath is None

    def test_info_file_defaults_empty(self):
        """--info-file defaults to empty list."""
        args = tyro.cli(Args, args=["run", "SPE-123"])

        assert isinstance(args, RunArgs)
        assert args.info_file == []

    def test_info_text_defaults_empty(self):
        """--info-text defaults to empty list."""
        args = tyro.cli(Args, args=["run", "SPE-123"])

        assert isinstance(args, RunArgs)
        assert args.info_text == []

    def test_info_file_single_value(self):
        """--info-file accepts a single path."""
        args = tyro.cli(Args, args=["run", "SPE-123", "--info-file", "/path/to/notes.md"])

        assert isinstance(args, RunArgs)
        assert args.info_file == [Path("/path/to/notes.md")]

    def test_info_file_multiple_values(self):
        """--info-file can be used multiple times."""
        args = tyro.cli(
            Args,
            args=[
                "run",
                "SPE-123",
                "--info-file",
                "/path/to/notes.md",
                "--info-file",
                "/path/to/patterns.md",
            ],
        )

        assert isinstance(args, RunArgs)
        assert args.info_file == [Path("/path/to/notes.md"), Path("/path/to/patterns.md")]

    def test_info_text_single_value(self):
        """--info-text accepts a single string."""
        args = tyro.cli(Args, args=["run", "SPE-123", "--info-text", "Focus on backend"])

        assert isinstance(args, RunArgs)
        assert args.info_text == ["Focus on backend"]

    def test_info_text_multiple_values(self):
        """--info-text can be used multiple times."""
        args = tyro.cli(
            Args,
            args=[
                "run",
                "SPE-123",
                "--info-text",
                "Focus on backend",
                "--info-text",
                "Add integration tests",
            ],
        )

        assert isinstance(args, RunArgs)
        assert args.info_text == ["Focus on backend", "Add integration tests"]

    def test_info_file_and_text_combined(self):
        """--info-file and --info-text can be used together."""
        args = tyro.cli(
            Args,
            args=[
                "run",
                "SPE-123",
                "--info-file",
                "/path/to/notes.md",
                "--info-text",
                "Focus on backend",
            ],
        )

        assert isinstance(args, RunArgs)
        assert args.info_file == [Path("/path/to/notes.md")]
        assert args.info_text == ["Focus on backend"]


class TestCleanupCommand:
    """Tests for the 'cleanup' command argument parsing."""

    def test_requires_ticket_key(self):
        """Cleanup command requires a ticket key."""
        with pytest.raises(SystemExit):
            tyro.cli(Args, args=["cleanup"])

    def test_parses_ticket_key(self):
        """Ticket key is parsed correctly."""
        args = tyro.cli(Args, args=["cleanup", "SPE-123"])

        assert isinstance(args, CleanupArgs)
        assert args.ticket == "SPE-123"


class TestTicketCommand:
    """Tests for the 'ticket' command argument parsing."""

    def test_requires_ticket_key(self):
        """Ticket command requires a ticket key."""
        with pytest.raises(SystemExit):
            tyro.cli(Args, args=["ticket"])

    def test_parses_ticket_key(self):
        """Ticket key is parsed correctly."""
        args = tyro.cli(Args, args=["ticket", "SPE-123"])

        assert isinstance(args, TicketArgs)
        assert args.ticket == "SPE-123"


class TestContextCommand:
    """Tests for the 'context' command and subcommands."""

    def test_context_show_default(self):
        """'context show' is parsed correctly."""
        args = tyro.cli(Args, args=["context", "show"])

        assert isinstance(args, ContextShowArgs)

    @pytest.mark.parametrize(
        ("cli_args", "expected_type"),
        [
            (["context", "show"], ContextShowArgs),
            (["context", "generate"], ContextGenerateArgs),
            (["context", "path"], ContextPathArgs),
        ],
    )
    def test_subcommands_parsed(self, cli_args, expected_type):
        """Context subcommands are parsed correctly."""
        args = tyro.cli(Args, args=cli_args)

        assert isinstance(args, expected_type)

    def test_generate_output_path(self):
        """--output flag in generate is converted to Path."""
        args = tyro.cli(Args, args=["context", "generate", "--output", "/custom/AGENT.md"])

        assert isinstance(args, ContextGenerateArgs)
        assert args.output == Path("/custom/AGENT.md")

    @pytest.mark.parametrize(
        ("cli_args", "attr", "expected"),
        [
            (["context", "generate", "--deep"], "deep", True),
            (["context", "generate", "--force"], "force", True),
            (["context", "generate"], "deep", False),
            (["context", "generate"], "force", False),
        ],
        ids=["deep-flag", "force-flag", "no-deep", "no-force"],
    )
    def test_generate_boolean_flags(self, cli_args, attr, expected):
        """Generate subcommand boolean flags work correctly."""
        args = tyro.cli(Args, args=cli_args)

        assert isinstance(args, ContextGenerateArgs)
        assert getattr(args, attr) == expected

    def test_show_output_path(self):
        """--output flag in show is converted to Path."""
        args = tyro.cli(Args, args=["context", "show", "--output", "/path/AGENT.md"])

        assert isinstance(args, ContextShowArgs)
        assert args.output == Path("/path/AGENT.md")


class TestHealthCommand:
    """Tests for the 'health' command argument parsing."""

    def test_health_defaults(self):
        """Health command has correct defaults."""
        args = tyro.cli(Args, args=["health"])

        assert isinstance(args, HealthArgs)
        assert args.full is False
        assert args.playwright is False
        assert args.timeout == 30

    def test_health_full_flag(self):
        """--full flag is parsed correctly."""
        args = tyro.cli(Args, args=["health", "--full"])

        assert isinstance(args, HealthArgs)
        assert args.full is True

    def test_health_playwright_flag(self):
        """--playwright flag is parsed correctly."""
        args = tyro.cli(Args, args=["health", "--playwright"])

        assert isinstance(args, HealthArgs)
        assert args.playwright is True

    def test_health_timeout(self):
        """--timeout value is parsed correctly."""
        args = tyro.cli(Args, args=["health", "--timeout", "60"])

        assert isinstance(args, HealthArgs)
        assert args.timeout == 60


class TestParserHelp:
    """Tests for help output (smoke tests)."""

    def test_main_help_exits_cleanly(self):
        """Main --help exits with code 0."""
        with pytest.raises(SystemExit) as exc_info:
            tyro.cli(Args, args=["--help"])

        assert exc_info.value.code == 0

    @pytest.mark.parametrize("command", ["run", "cleanup", "ticket", "health"])
    def test_subcommand_help_exits_cleanly(self, command):
        """Subcommand --help exits with code 0."""
        with pytest.raises(SystemExit) as exc_info:
            tyro.cli(Args, args=[command, "--help"])

        assert exc_info.value.code == 0

    def test_context_subcommand_help_exits_cleanly(self):
        """Context subcommand --help exits with code 0."""
        with pytest.raises(SystemExit) as exc_info:
            tyro.cli(Args, args=["context", "--help"])

        assert exc_info.value.code == 0
