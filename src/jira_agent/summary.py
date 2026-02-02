"""Agent summary markdown generation."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jira_agent.agent import AgentResult
from jira_agent.integrations import Ticket


@dataclass
class SummaryOptions:
    """Options for summary generation."""

    include_metadata: bool = False
    output_path: Path | None = None  # None = worktree root
    to_contexts: bool = False


@dataclass
class SummaryContext:
    """Context for summary generation."""

    ticket: Ticket
    result: AgentResult
    worktree_path: Path
    branch_name: str | None
    duration_seconds: int
    context_file: Path
    jira_url: str  # Base URL for ticket links


def generate_summary(ctx: SummaryContext, options: SummaryOptions) -> str:
    """Generate markdown summary content.

    Args:
        ctx: Context containing ticket, result, and execution details.
        options: Options controlling summary content.

    Returns:
        Markdown string with the summary content.
    """
    lines: list[str] = []

    # Header
    lines.append(f"# Agent Summary: {ctx.ticket.key}")
    lines.append("")

    # Ticket section
    lines.append("## Ticket")
    lines.append(f"**{ctx.ticket.key}**: {ctx.ticket.summary}")
    lines.append("")

    # Implementation section
    lines.append("## Implementation")
    lines.append(ctx.result.summary)
    lines.append("")

    # Files Changed section
    if ctx.result.files:
        lines.append(f"## Files Changed ({len(ctx.result.files)})")
        for f in ctx.result.files:
            # Make path relative if it starts with worktree path
            rel_path = f
            worktree_str = str(ctx.worktree_path)
            if f.startswith(worktree_str):
                rel_path = f[len(worktree_str) :].lstrip("/")
            lines.append(f"- {rel_path}")
        lines.append("")

    # Status section
    lines.append("## Status")
    if ctx.result.success:
        verification = ctx.result.verification_status
        if verification == "complete":
            lines.append("Complete")
        elif verification == "partial":
            lines.append("Partial")
        else:
            lines.append("Done")
    else:
        lines.append("Failed")
    lines.append("")

    # Remaining Work section
    lines.append("## Remaining Work")
    if ctx.result.remaining_work:
        for item in ctx.result.remaining_work:
            lines.append(f"- {item}")
    else:
        lines.append("(none)")
    lines.append("")

    # Optional Metadata section
    if options.include_metadata:
        lines.append("---")
        lines.append("## Metadata")
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"- **Generated**: {timestamp}")
        lines.append(f"- **Duration**: {ctx.duration_seconds}s")
        lines.append(f"- **Worktree**: {ctx.worktree_path}")
        if ctx.branch_name:
            lines.append(f"- **Branch**: {ctx.branch_name}")
        lines.append(f"- **Ticket Type**: {ctx.ticket.issue_type}")
        lines.append(f"- **Ticket Priority**: {ctx.ticket.priority}")
        # Construct ticket URL
        ticket_url = f"{ctx.jira_url.rstrip('/')}/browse/{ctx.ticket.key}"
        lines.append(f"- **Ticket URL**: {ticket_url}")
        lines.append(f"- **Context File**: {ctx.context_file}")
        lines.append("")

    return "\n".join(lines)


def _version_existing_summary(path: Path) -> None:
    """Rename existing summary files with version suffix.

    If AGENT_SUMMARY.md exists, renames it to AGENT_SUMMARY.1.md (or .2.md, etc).

    Args:
        path: Path to the summary file.
    """
    if not path.exists():
        return

    # Find next available version number
    version = 1
    parent = path.parent
    stem = path.stem  # e.g., "AGENT_SUMMARY"
    suffix = path.suffix  # e.g., ".md"

    while True:
        versioned_path = parent / f"{stem}.{version}{suffix}"
        if not versioned_path.exists():
            break
        version += 1

    # Rename current file to versioned name
    path.rename(versioned_path)


def _get_output_path(
    ctx: SummaryContext,
    options: SummaryOptions,
    contexts_dir: Path | None = None,
) -> Path:
    """Determine the output path for the summary file.

    Args:
        ctx: Summary context.
        options: Summary options.
        contexts_dir: Base contexts directory (for to_contexts mode).

    Returns:
        Path where the summary should be written.
    """
    if options.output_path:
        # Explicit path provided
        return options.output_path

    if options.to_contexts:
        # Output to contexts/{repo_name}/{ticket_id}/AGENT_SUMMARY.md
        if contexts_dir is None:
            # Default to contexts/ in current working directory
            contexts_dir = Path.cwd() / "contexts"

        # Extract repo name from worktree path
        repo_name = ctx.worktree_path.name

        summary_dir = contexts_dir / repo_name / ctx.ticket.key
        summary_dir.mkdir(parents=True, exist_ok=True)

        return summary_dir / "AGENT_SUMMARY.md"

    # Default: worktree root
    return ctx.worktree_path / "AGENT_SUMMARY.md"


def write_summary(
    ctx: SummaryContext,
    options: SummaryOptions,
    contexts_dir: Path | None = None,
) -> Path:
    """Write summary to appropriate location.

    Args:
        ctx: Summary context.
        options: Summary options.
        contexts_dir: Base contexts directory (for to_contexts mode).

    Returns:
        Path where the summary was written.
    """
    output_path = _get_output_path(ctx, options, contexts_dir)

    # Version existing file if outputting to contexts
    if options.to_contexts:
        _version_existing_summary(output_path)

    # Generate and write content
    content = generate_summary(ctx, options)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)

    return output_path
