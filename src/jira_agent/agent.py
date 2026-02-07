"""Claude agent using the Agent SDK for code exploration and modification."""

import anyio
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import re
from collections.abc import Callable
from typing import Any

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from jira_agent.integrations import Ticket
from jira_agent.log import log, print  # noqa: A004
from jira_agent.hooks import AuditLogger, make_audit_hook, make_security_hook
from jira_agent.prompts import (
    BROWSER_VERIFICATION_SCHEMA,
    RESULT_SCHEMA,
    build_ticket_prompt,
    get_browser_verifier_prompt,
    get_implementation_prompt,
    get_planner_prompt,
    get_verifier_prompt,
)


@dataclass
class AgentResult:
    """Result from running the agent on a ticket."""

    success: bool
    summary: str
    files: list[str] = field(default_factory=list)
    verification_status: str = "unknown"
    remaining_work: list[str] = field(default_factory=list)


class ProgressTracker:
    """Tracks and logs agent progress."""

    start_time: datetime

    def __init__(self):
        self.start_time = datetime.now()

    def log(self, msg: str):
        elapsed = (datetime.now() - self.start_time).seconds
        print(f"  [{elapsed:3d}s] {msg}")


# --- Hooks ---


def make_file_change_logger(worktree: Path):
    """Create a hook that logs file changes relative to the worktree.

    Args:
        worktree: Path to the working directory (worktree or repo).

    Returns:
        An async hook function for logging file modifications.
    """
    worktree_str = str(worktree)

    async def log_file_changes(
        input_data: dict[str, dict[str, Any]], _tool_use_id: str, _context: Any
    ) -> dict[str, Any]:
        """Hook to log file modifications."""
        tool_input: dict[str, str] = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if file_path:
            # Make path relative to worktree for cleaner output
            if file_path.startswith(worktree_str):
                file_path = file_path[len(worktree_str) :].lstrip("/")
            print(f"  📝 Modifying: {file_path}")
        return {}

    return log_file_changes


# --- Agent Configuration ---


def build_agent_options(
    worktree: Path,
    max_turns: int,
    codebase_context: str,
    audit_logger: AuditLogger | None = None,
    enable_security_hook: bool = True,
) -> ClaudeAgentOptions:
    """Build the agent configuration options.

    Args:
        worktree: Path to the working directory for the agent.
        max_turns: Maximum number of conversation turns.
        codebase_context: The loaded AGENT.md content to inject into prompts.
        audit_logger: Optional AuditLogger for logging all tool calls.
        enable_security_hook: Whether to enable security checks (default True).

    Returns:
        Configured agent options.
    """
    # Build hooks list
    pre_tool_hooks: list[HookMatcher] = []

    # Security hook runs FIRST to block dangerous operations
    if enable_security_hook:
        pre_tool_hooks.append(
            HookMatcher(matcher="Edit|Write|Bash|NotebookEdit", hooks=[make_security_hook()])  # pyright: ignore[reportArgumentType]
        )

    # Add audit hook if logger provided (matches all tools)
    if audit_logger:
        pre_tool_hooks.append(
            HookMatcher(matcher=".*", hooks=[make_audit_hook(audit_logger)])  # pyright: ignore[reportArgumentType]
        )

    # Add file change logger for Edit/Write tools
    pre_tool_hooks.append(
        HookMatcher(matcher="Edit|Write", hooks=[make_file_change_logger(worktree)])  # pyright: ignore[reportArgumentType]
    )

    return ClaudeAgentOptions(
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": get_implementation_prompt(codebase_context),
        },
        allowed_tools=["Read", "Edit", "Write", "Glob", "Grep", "Bash", "Task"],
        permission_mode="acceptEdits",
        cwd=str(worktree),
        max_turns=max_turns,
        agents={
            "planner": AgentDefinition(
                description="Analyzes tickets and creates comprehensive implementation plans. Use this FIRST before making any changes.",
                prompt=get_planner_prompt(codebase_context),
                tools=["Read", "Glob", "Grep"],
                model="sonnet",
            ),
            "verifier": AgentDefinition(
                description="Verifies implementation completeness. Use this AFTER making all changes.",
                prompt=get_verifier_prompt(codebase_context),
                tools=["Read", "Glob", "Grep", "Bash"],
                model="sonnet",
            ),
        },
        hooks={"PreToolUse": pre_tool_hooks} if pre_tool_hooks else {},
        output_format={"type": "json_schema", "schema": RESULT_SCHEMA},
    )


# --- Message Handlers ---


def handle_text_block(block: TextBlock, tracker: ProgressTracker) -> None:
    """Handle a text block from the assistant."""
    text = block.text.strip()
    if not text:
        return

    lines = text.split("\n")
    for line in lines[:3]:
        if line.strip():
            tracker.log(f"💭 {line[:80]}...")
    if len(lines) > 3:
        tracker.log(f"💭 ... ({len(lines) - 3} more lines)")


def handle_tool_use(block: ToolUseBlock, tracker: ProgressTracker, files_modified: list[str]) -> None:
    """Handle a tool use block from the assistant."""
    tool_name = block.name
    tool_input = block.input or {}

    if tool_name == "Task":
        subagent = tool_input.get("subagent_type", "unknown")
        tracker.log(f"🚀 Launching subagent: {subagent}")
    elif tool_name in ("Edit", "Write"):
        path = tool_input.get("file_path", "")
        if path:
            files_modified.append(path)
    elif tool_name == "Read":
        path = tool_input.get("file_path", "")
        short_path = path.split("/")[-1] if path else ""
        tracker.log(f"📖 Read: {short_path}")
    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        tracker.log(f"🔍 Glob: {pattern}")
    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        tracker.log(f"🔎 Grep: {pattern[:50]}...")
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        tracker.log(f"⚡ Bash: {cmd[:50]}...")


def handle_result(message: ResultMessage, files_modified: list[str]) -> AgentResult:
    """Handle a result message and return the appropriate AgentResult."""
    if message.is_error:
        print(f"\n❌ Error: {message.result or message.subtype}")
        return AgentResult(
            success=False,
            summary=message.result or f"Agent error: {message.subtype}",
            files=list(set(files_modified)),
        )

    print(f"\n✅ Completed: {message.subtype}")

    if hasattr(message, "structured_output") and message.structured_output:
        output = message.structured_output
        return AgentResult(
            success=True,
            summary=output.get("summary", "Completed"),
            files=output.get("files_modified", []) + output.get("files_created", []),
            verification_status=output.get("verification_status", "unknown"),
            remaining_work=output.get("remaining_work", []),
        )

    return AgentResult(
        success=True,
        summary=message.result or "Completed",
        files=list(set(files_modified)),
    )


# --- Main Agent ---


async def run_agent(
    worktree: Path,
    ticket: Ticket,
    context_path: Path,
    max_turns: int = 100,
    additional_info: str | None = None,
    audit_logger: AuditLogger | None = None,
) -> AgentResult:
    """Run the agent to fix a Jira ticket.

    Args:
        worktree: Path to the working directory (worktree or repo).
        ticket: The Jira ticket to implement.
        context_path: Path to the AGENT.md context file.
        max_turns: Maximum number of conversation turns.
        additional_info: Optional additional context from --info.file/--info.text.
        audit_logger: Optional AuditLogger for logging all tool calls.

    Returns:
        AgentResult with implementation status and details.
    """
    from jira_agent.context import load_context

    print(f"\n{'=' * 60}")
    print("🤖 Agent starting")
    print(f"   Ticket: {ticket.key}")
    print(f"   Worktree: {worktree}")
    print(f"   Context: {context_path}")
    print(f"   Max turns: {max_turns}")
    print(f"{'=' * 60}\n")

    # Load codebase context
    codebase_context = load_context(context_path)

    tracker = ProgressTracker()
    files_modified: list[str] = []
    prompt = build_ticket_prompt(ticket, additional_info=additional_info)
    options = build_agent_options(worktree, max_turns, codebase_context, audit_logger)

    result: AgentResult | None = None
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        handle_text_block(block, tracker)
                    elif isinstance(block, ToolUseBlock):
                        handle_tool_use(block, tracker, files_modified)

            elif isinstance(message, ResultMessage):
                result = handle_result(message, files_modified)
                break  # Exit loop properly to allow generator cleanup

    except Exception as e:
        print(f"\n❌ Exception: {e}")
        log.exception("Agent failed with unexpected error")
        return AgentResult(
            success=False,
            summary=str(e),
            files=list(set(files_modified)),
        )

    if result:
        return result

    return AgentResult(
        success=False,
        summary="Agent finished without explicit result",
        files=list(set(files_modified)),
    )


def run(
    worktree: Path,
    ticket: Ticket,
    context_path: Path,
    max_turns: int = 100,
    additional_info: str | None = None,
    audit_logger: AuditLogger | None = None,
) -> AgentResult:
    """Synchronous wrapper for run_agent.

    Args:
        worktree: Path to the working directory (worktree or repo).
        ticket: The Jira ticket to implement.
        context_path: Path to the AGENT.md context file.
        max_turns: Maximum number of conversation turns.
        additional_info: Optional additional context from --info.file/--info.text.
        audit_logger: Optional AuditLogger for logging all tool calls.

    Returns:
        AgentResult with implementation status and details.
    """
    return anyio.run(run_agent, worktree, ticket, context_path, max_turns, additional_info, audit_logger)


# --- Browser Verification ---


@dataclass
class BrowserVerificationResult:
    """Result from browser verification."""

    url_visited: str
    observed: str
    confidence: str  # verified, likely-working, uncertain, broken
    expected: str = ""
    reasoning: str = ""


def build_browser_prompt(ticket: Ticket, base_url: str) -> str:
    """Build the prompt for browser verification.

    Args:
        ticket: The Jira ticket that was implemented.
        base_url: The base URL of the deployed application.

    Returns:
        Prompt instructing the agent to verify the implementation.
    """
    return f"""Verify that this Jira ticket was implemented correctly in the deployed application:

# {ticket.key}: {ticket.summary}

## Description
{ticket.description or "(no description)"}

## Base URL
{base_url}

## Instructions

1. Based on the ticket, determine which page/feature to check
2. Navigate to the relevant page using browser_navigate
3. Take an accessibility snapshot using browser_snapshot
4. Describe what you observe
5. Assess whether the implementation appears correct

Report your findings with a confidence level: verified, likely-working, uncertain, or broken.
"""


async def run_browser_verification(
    ticket: Ticket,
    context_path: Path,
    base_url: str,
    max_turns: int = 20,
) -> BrowserVerificationResult:
    """Run browser verification using Playwright MCP.

    Args:
        ticket: The Jira ticket that was implemented.
        context_path: Path to the AGENT.md context file.
        base_url: The base URL of the deployed application.
        max_turns: Maximum conversation turns for verification.

    Returns:
        BrowserVerificationResult with verification details.
    """
    from jira_agent.context import load_context

    print("\n" + "=" * 60)
    print("🌐 Browser Verification")
    print(f"   Ticket: {ticket.key}")
    print(f"   URL: {base_url}")
    print("=" * 60 + "\n")

    codebase_context = load_context(context_path)
    prompt = build_browser_prompt(ticket, base_url)

    # Playwright MCP tools
    playwright_tools = [
        "mcp__plugin_playwright_playwright__browser_navigate",
        "mcp__plugin_playwright_playwright__browser_snapshot",
        "mcp__plugin_playwright_playwright__browser_click",
        "mcp__plugin_playwright_playwright__browser_type",
        "mcp__plugin_playwright_playwright__browser_take_screenshot",
        "mcp__plugin_playwright_playwright__browser_press_key",
    ]

    options = ClaudeAgentOptions(
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": get_browser_verifier_prompt(codebase_context, base_url),
        },
        allowed_tools=playwright_tools,
        permission_mode="default",
        max_turns=max_turns,
        output_format={"type": "json_schema", "schema": BROWSER_VERIFICATION_SCHEMA},
    )

    result: BrowserVerificationResult | None = None
    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text = block.text.strip()
                        if text:
                            print(f"  🔍 {text[:100]}...")
                    elif isinstance(block, ToolUseBlock):
                        tool_name = block.name.split("__")[-1]  # Get last part
                        print(f"  🎭 {tool_name}")

            elif isinstance(message, ResultMessage):
                if message.is_error:
                    result = BrowserVerificationResult(
                        url_visited="unknown",
                        observed=f"Error: {message.result or message.subtype}",
                        confidence="broken",
                    )
                elif hasattr(message, "structured_output") and message.structured_output:
                    output = message.structured_output
                    result = BrowserVerificationResult(
                        url_visited=output.get("url_visited", "unknown"),
                        observed=output.get("observed", ""),
                        confidence=output.get("confidence", "uncertain"),
                        expected=output.get("expected", ""),
                        reasoning=output.get("reasoning", ""),
                    )
                else:
                    result = BrowserVerificationResult(
                        url_visited="unknown",
                        observed=message.result or "Completed",
                        confidence="uncertain",
                    )
                break  # Exit loop properly to allow generator cleanup

    except Exception as e:
        print(f"\n❌ Browser verification error: {e}")
        log.exception("Browser verification failed")
        return BrowserVerificationResult(
            url_visited="unknown",
            observed=str(e),
            confidence="broken",
        )

    if result:
        return result

    return BrowserVerificationResult(
        url_visited="unknown",
        observed="Verification ended without result",
        confidence="uncertain",
    )


def run_browser_verify(
    ticket: Ticket, context_path: Path, base_url: str, max_turns: int = 20
) -> BrowserVerificationResult:
    """Synchronous wrapper for run_browser_verification.

    Args:
        ticket: The Jira ticket that was implemented.
        context_path: Path to the AGENT.md context file.
        base_url: The base URL of the deployed application.
        max_turns: Maximum conversation turns for verification.

    Returns:
        BrowserVerificationResult with verification details.
    """
    return anyio.run(run_browser_verification, ticket, context_path, base_url, max_turns)


# --- Worktree Management ---


def create_worktree(
    repo: Path,
    worktrees_dir: Path,
    ticket_key: str,
    base_commit: str | None = None,
) -> tuple[Path, str]:
    """Create git worktree for ticket. Returns (path, branch).

    Args:
        repo: Path to the main repository.
        worktrees_dir: Path to the worktrees directory.
        ticket_key: Jira ticket key (e.g., "SPE-123").
        base_commit: If provided, create worktree from this commit instead of
                     origin/main. Useful for evaluation against historical PRs.
    """
    slug = ticket_key.lower().replace(" ", "-")
    branch = f"fix/{slug}"
    wt_path = worktrees_dir / slug

    worktrees_dir.mkdir(parents=True, exist_ok=True)

    if wt_path.exists():
        print(f"  Worktree exists: {wt_path}")
        return wt_path, branch

    _ = subprocess.run(["git", "fetch", "origin"], cwd=repo, check=True, capture_output=True)

    # Determine starting point
    if base_commit:
        start_point = base_commit
        print(f"  Starting from commit: {base_commit[:8]}...")
    else:
        # Get default branch
        r = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        default = r.stdout.strip().replace("refs/remotes/origin/", "") if r.returncode == 0 else "main"
        start_point = f"origin/{default}"

    _ = subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(wt_path), start_point],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    print(f"  Created: {wt_path} ({branch})")
    return wt_path, branch


def remove_worktree(repo: Path, worktrees_dir: Path, ticket_key: str) -> None:
    """Remove worktree and branch."""
    slug = ticket_key.lower().replace(" ", "-")
    wt_path = worktrees_dir / slug

    if wt_path.exists():
        _ = subprocess.run(
            ["git", "worktree", "remove", str(wt_path), "--force"],
            cwd=repo,
            check=True,
        )

    # Branch deletion may fail if branch doesn't exist - that's OK
    _ = subprocess.run(["git", "branch", "-D", f"fix/{slug}"], cwd=repo, capture_output=True)
    print(f"  Removed worktree for {ticket_key}")


# --- Branch Management (Alternative to Worktrees) ---


def slugify_summary(summary: str, max_len: int = 50) -> str:
    """Convert ticket summary to URL-safe slug.

    Args:
        summary: Ticket summary text (e.g., "Cost Code Descriptions not Populating")
        max_len: Maximum length for the slug

    Returns:
        Lowercased, hyphenated slug (e.g., "cost-code-descriptions-not-populating")
    """
    # Lowercase and replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", summary.lower())
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    # Truncate to max length, avoiding cut-off mid-word
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    return slug


def _get_default_branch(repo: Path) -> str:
    """Get the default branch name for a repository."""
    r = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        return r.stdout.strip().replace("refs/remotes/origin/", "")
    return "main"


def _has_uncommitted_changes(repo: Path) -> bool:
    """Check if the repository has uncommitted changes."""
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return bool(r.stdout.strip())


def _branch_exists(repo: Path, branch: str) -> tuple[bool, bool]:
    """Check if branch exists locally and/or remotely.

    Returns:
        (exists_locally, exists_remotely)
    """
    # Check local
    local = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        cwd=repo,
        capture_output=True,
    )
    exists_locally = local.returncode == 0

    # Check remote
    remote = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", branch],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    exists_remotely = bool(remote.stdout.strip())

    return exists_locally, exists_remotely


def setup_branch(
    repo: Path,
    branch_name: str | None,
    ticket: Ticket,
    confirm_existing: Callable[[], bool],
    base_commit: str | None = None,
) -> tuple[Path, str]:
    """Setup branch for in-repo work. Returns (repo_path, branch_name).

    This is an alternative to create_worktree() that works directly in the
    main repository, making it easier for devs to deploy and test changes.

    Args:
        repo: Path to main repository
        branch_name: Explicit branch name, or None to auto-generate from ticket
        ticket: Ticket object (used for auto-generating branch name)
        confirm_existing: Callback to ask user if they want to use existing branch
        base_commit: If provided, create branch from this commit instead of
                     origin/main. Useful for evaluation against historical PRs.

    Returns:
        Tuple of (repo_path, branch_name)

    Raises:
        RuntimeError: If uncommitted changes exist or user declines to use existing branch
    """
    # Generate branch name if not provided
    if branch_name is None:
        slug = slugify_summary(ticket.summary)
        branch_name = f"{ticket.key}-{slug}"

    print(f"  Branch: {branch_name}")

    # Check for uncommitted changes
    if _has_uncommitted_changes(repo):
        raise RuntimeError("Uncommitted changes in repository. Please commit or stash before continuing.")

    # Fetch latest from origin
    print("  Fetching from origin...")
    _ = subprocess.run(["git", "fetch", "origin"], cwd=repo, check=True, capture_output=True)

    # Check if branch exists
    exists_local, exists_remote = _branch_exists(repo, branch_name)

    if exists_local or exists_remote:
        print(f"  Branch '{branch_name}' already exists.")
        if not confirm_existing():
            raise RuntimeError("User declined to use existing branch.")

        # Checkout existing branch
        if exists_local:
            _ = subprocess.run(
                ["git", "checkout", branch_name],
                cwd=repo,
                check=True,
                capture_output=True,
            )
        else:
            # Track remote branch
            _ = subprocess.run(
                ["git", "checkout", "-b", branch_name, f"origin/{branch_name}"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
        print(f"  Checked out existing branch: {branch_name}")
    else:
        # Create new branch from specified commit or default branch
        if base_commit:
            start_point = base_commit
            print(f"  Creating branch from commit {base_commit[:8]}...")
        else:
            default_branch = _get_default_branch(repo)
            start_point = f"origin/{default_branch}"
            print(f"  Creating branch from origin/{default_branch}...")

        _ = subprocess.run(
            ["git", "checkout", "-b", branch_name, start_point],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        print(f"  Created and checked out: {branch_name}")

    return repo, branch_name
