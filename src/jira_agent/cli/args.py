"""CLI argument dataclasses for tyro."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Union

import tyro


@dataclass
class RunArgs:
    """Process a Jira ticket.

    Fetches the ticket from Jira and uses Claude to implement the required changes.
    """

    ticket: Annotated[str, tyro.conf.Positional]
    """Jira ticket key (e.g., SPE-123)."""

    dry_run: bool = False
    """Show ticket without processing."""

    no_pr: bool = False
    """Skip PR creation."""

    branch: str | None = None
    """Work in main repo instead of worktree. Optionally specify branch name."""

    context: Path | None = None
    """Use specific context file."""

    base_commit: str | None = None
    """Start from specific commit (for evaluation)."""

    verify: bool = False
    """Run browser verification after implementation (requires --branch)."""

    verify_url: str = "http://localhost:3000"
    """Base URL for browser verification."""

    summary: bool = False
    """Generate AGENT_SUMMARY.md with implementation details."""

    summary_metadata: bool = False
    """Include metadata (timestamp, duration, etc.) in summary."""

    summary_to_contexts: bool = False
    """Write summary to contexts/{repo}/{ticket}/ with versioning."""

    summary_filepath: Path | None = None
    """Write summary to custom filepath."""

    info_file: Annotated[list[Path], tyro.conf.UseAppendAction] = field(default_factory=list)
    """Additional context from file(s). Can be used multiple times."""

    info_text: Annotated[list[str], tyro.conf.UseAppendAction] = field(default_factory=list)
    """Additional context text. Can be used multiple times."""

    audit_log: Path | None = None
    """Path to write audit log of all tool calls (JSON format)."""

    audit_stderr: bool = False
    """Also print audit log entries to stderr."""


@dataclass
class CleanupArgs:
    """Remove a worktree."""

    ticket: Annotated[str, tyro.conf.Positional]
    """Jira ticket key."""


@dataclass
class TicketArgs:
    """Show ticket details."""

    ticket: Annotated[str, tyro.conf.Positional]
    """Jira ticket key."""


@dataclass
class ContextShowArgs:
    """Show context content."""

    output: Path | None = None
    """Path to context file."""


@dataclass
class ContextGenerateArgs:
    """Generate context from repo."""

    output: Path | None = None
    """Output path (default: contexts/{repo}/AGENT.md)."""

    deep: bool = False
    """AI-powered deep analysis."""

    force: bool = False
    """Overwrite existing."""


@dataclass
class ContextPathArgs:
    """Show default context path for current repo."""

    pass


# Context subcommand type - for nested context show/generate/path
ContextArgs = Union[
    Annotated[ContextShowArgs, tyro.conf.subcommand(name="show", default=True)],
    Annotated[ContextGenerateArgs, tyro.conf.subcommand(name="generate")],
    Annotated[ContextPathArgs, tyro.conf.subcommand(name="path")],
]


@dataclass
class HealthArgs:
    """Check configuration and connectivity."""

    full: bool = False
    """Also run connectivity checks (slower, requires network)."""

    playwright: bool = False
    """Include Playwright MCP in connectivity checks (requires --full)."""

    timeout: int = 30
    """Timeout for each connectivity check in seconds."""


# Main CLI type - Union of all commands
# Use directly with tyro.cli() for clean subcommand syntax: `jira-agent run SPE-123`
Args = Union[
    Annotated[RunArgs, tyro.conf.subcommand(name="run")],
    Annotated[CleanupArgs, tyro.conf.subcommand(name="cleanup")],
    Annotated[TicketArgs, tyro.conf.subcommand(name="ticket")],
    Annotated[ContextArgs, tyro.conf.subcommand(name="context")],
    Annotated[HealthArgs, tyro.conf.subcommand(name="health")],
]
