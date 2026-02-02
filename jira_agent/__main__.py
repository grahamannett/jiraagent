"""CLI entry point."""

import sys
import time

import tyro

from jira_agent.agent import (
    create_worktree,
    remove_worktree,
    run,
    run_browser_verify,
    setup_branch,
)
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
from jira_agent.config import Config
from jira_agent.context import (
    context_exists,
    generate_context,
    get_context_path_for_repo,
    get_default_context_dir,
    load_context,
)
from jira_agent.integrations import (
    HealthCheckResult,
    HealthStatus,
    fetch_ticket,
    run_config_checks,
    run_health_checks_sync,
)
from jira_agent.hooks import AuditLogger
from jira_agent.log import print  # noqa: A004
from jira_agent.validation import ValidationError, validate_ticket_key


def _confirm_existing_branch() -> bool:
    """Prompt user to confirm using existing branch."""
    response = input("  Use existing branch? [y/N] ").strip().lower()
    return response in ("y", "yes")


def _wait_for_deployment() -> bool:
    """Prompt user to deploy and continue with browser verification.

    Returns:
        True if user pressed Enter, False if cancelled (Ctrl+C or EOF).
    """
    print("\n" + "=" * 60)
    print("READY FOR BROWSER VERIFICATION")
    print("=" * 60)
    print("\nPlease deploy your changes now.")
    print("Press Enter when the app is running (Ctrl+C to skip)...")
    try:
        input()
        return True
    except (EOFError, KeyboardInterrupt):
        return False


# --- Command Handlers ---


def _load_additional_info(args: RunArgs) -> str | None:
    """Load and combine additional context from --info.file and --info.text args.

    Returns:
        Combined context string, or None if no additional info provided.
    """
    parts: list[str] = []

    # Load file contents
    for file_path in args.info_file:
        if not file_path.exists():
            sys.exit(f"Error: Info file not found: {file_path}")
        try:
            content = file_path.read_text().strip()
            if content:
                parts.append(f"# From {file_path.name}\n{content}")
        except OSError as e:
            sys.exit(f"Error reading info file {file_path}: {e}")

    # Add text inputs
    for text in args.info_text:
        if text.strip():
            parts.append(text.strip())

    if not parts:
        return None

    return "\n\n".join(parts)


def cmd_run(cfg: Config, args: RunArgs) -> None:
    """Process a Jira ticket."""
    # Validate ticket key format
    try:
        validate_ticket_key(args.ticket)
    except ValidationError as e:
        sys.exit(f"Error: {e}")

    # Validate --verify requires --branch
    if args.verify and args.branch is None:
        sys.exit("Error: --verify requires --branch mode (worktrees don't support deployment)")

    print(f"\nProcessing {args.ticket}\n")

    # Resolve context path
    context_path = args.context or get_context_path_for_repo(cfg.repo)

    if not context_path.exists():
        sys.exit(f"Context file not found: {context_path}. Run `jira-agent context generate`.")

    # Fetch ticket (via Atlassian MCP)
    print("Fetching ticket...")
    ticket = fetch_ticket(args.ticket)
    print(f"  {ticket.summary}")
    print(f"  {ticket.issue_type} | {ticket.priority} | {ticket.status}\n")

    if args.dry_run:
        print("Description:")
        print(ticket.description or "(none)")
        return

    # Setup working directory (branch or worktree)
    # args.branch is None if not specified, empty string if --branch with no value,
    # or the branch name if --branch NAME
    use_branch = args.branch is not None
    branch_name = args.branch if args.branch else None

    if use_branch:
        print("Setting up branch...")
        try:
            work_path, branch = setup_branch(
                cfg.repo,
                branch_name,
                ticket,
                _confirm_existing_branch,
                args.base_commit,
            )
        except RuntimeError as e:
            sys.exit(f"Error: {e}")
    else:
        print("Creating worktree...")
        work_path, branch = create_worktree(cfg.repo, cfg.worktrees, args.ticket, args.base_commit)

    # Load additional context if provided
    additional_info = _load_additional_info(args)
    if additional_info:
        print("Additional context provided via --info.file/--info.text")

    # Setup audit logger if requested
    audit_logger: AuditLogger | None = None
    if args.audit_log or args.audit_stderr:
        audit_logger = AuditLogger(
            output_path=args.audit_log,
            stderr=args.audit_stderr,
        )
        if args.audit_log:
            print(f"Audit logging to: {args.audit_log}")
        if args.audit_stderr:
            print("Audit logging to stderr")

    # Run agent (uses Claude Agent SDK with subagents)
    start_time = time.monotonic()
    try:
        result = run(
            work_path,
            ticket,
            context_path,
            additional_info=additional_info,
            audit_logger=audit_logger,
        )
    finally:
        if audit_logger:
            audit_logger.close()
    duration_seconds = int(time.monotonic() - start_time)

    print(f"\n{'=' * 60}")
    if result.success:
        print(f"DONE: {result.summary}")
        print(f"\nFiles Modified ({len(result.files)}):")
        for f in result.files:
            print(f"   - {f}")
        print(f"\nVerification: {result.verification_status}")
        if result.remaining_work:
            print("\nRemaining Work:")
            for item in result.remaining_work:
                print(f"   - {item}")
        if use_branch:
            print(f"\n Branch: {branch}")
            print(f" Repository: {work_path}")
            print("\nNext steps:")
            print("  git push -u origin HEAD   # Push branch to remote")
            print("  # Deploy to your dev environment")
        else:
            print(f"\nWorktree: {work_path}")
        if not args.no_pr:
            print("\n(PR creation not implemented yet)")

        # Browser verification (only available with --branch)
        if args.verify:
            if _wait_for_deployment():
                browser_result = run_browser_verify(ticket, context_path, args.verify_url)
                print("\nBrowser Verification:")
                print(f"   URL: {browser_result.url_visited}")
                print(f"   Observed: {browser_result.observed}")
                print(f"   Confidence: {browser_result.confidence}")
                if browser_result.reasoning:
                    print(f"   Reasoning: {browser_result.reasoning}")
            else:
                print("\nSkipping browser verification")
    else:
        print(f"FAILED: {result.summary}")
        if result.files:
            print("\nFiles touched before failure:")
            for f in result.files:
                print(f"   - {f}")

    # Write summary if requested
    if args.summary or args.summary_metadata or args.summary_to_contexts or args.summary_filepath:
        from jira_agent.summary import SummaryContext, SummaryOptions, write_summary

        summary_ctx = SummaryContext(
            ticket=ticket,
            result=result,
            worktree_path=work_path,
            branch_name=branch if use_branch else None,
            duration_seconds=duration_seconds,
            context_file=context_path,
            jira_url=cfg.jira_url,
        )

        summary_options = SummaryOptions(
            include_metadata=args.summary_metadata,
            output_path=args.summary_filepath,
            to_contexts=args.summary_to_contexts,
        )

        summary_path = write_summary(summary_ctx, summary_options, get_default_context_dir())
        print(f"\nSummary written to: {summary_path}")

    print("=" * 60)


def cmd_cleanup(cfg: Config, args: CleanupArgs) -> None:
    """Remove a worktree."""
    # Validate ticket key format
    try:
        validate_ticket_key(args.ticket)
    except ValidationError as e:
        sys.exit(f"Error: {e}")

    remove_worktree(cfg.repo, cfg.worktrees, args.ticket)


def cmd_ticket(cfg: Config, args: TicketArgs) -> None:
    """Show ticket details."""
    # Validate ticket key format
    try:
        validate_ticket_key(args.ticket)
    except ValidationError as e:
        sys.exit(f"Error: {e}")

    ticket = fetch_ticket(args.ticket)
    print(f"\n{ticket.key}: {ticket.summary}")
    print(f"{ticket.issue_type} | {ticket.priority} | {ticket.status}\n")
    print(ticket.description or "(no description)")


def cmd_context_show(cfg: Config, args: ContextShowArgs) -> None:
    """Show context content."""
    default_path = get_context_path_for_repo(cfg.repo)
    output_path = args.output or default_path

    if not context_exists(output_path):
        sys.exit(f"Context file not found: {output_path}\nRun 'jira-agent context generate' to create it.")
    content = load_context(output_path)
    print(content)


def cmd_context_generate(cfg: Config, args: ContextGenerateArgs) -> None:
    """Generate context from repo."""
    default_path = get_context_path_for_repo(cfg.repo)
    output_path = args.output or default_path

    if context_exists(output_path) and not args.force:
        print(f"Context file already exists: {output_path}")
        print("Use --force to overwrite.")
        return

    print(f"Generating context for: {cfg.repo}")
    print(f"Output: {output_path}")
    if args.deep:
        print("Using AI-powered deep analysis (this may take several minutes)...")

    content = generate_context(cfg.repo, output_path, deep=args.deep)

    if not content:
        print("Generation failed or returned empty content")
        return

    print(f"\nGenerated: {output_path}")
    print("\nPreview (first 50 lines):")
    for line in content.split("\n")[:50]:
        print(f"  {line}")


def cmd_context_path(cfg: Config, _args: ContextPathArgs) -> None:
    """Show default context path for current repo."""
    print(get_context_path_for_repo(cfg.repo))


def _print_health_results(results: list[HealthCheckResult], label: str) -> bool:
    """Print health check results and return True if all passed."""
    if not results:
        print(f"  No {label.lower()} checks available.")
        return True

    all_ok = True
    for result in results:
        if result.status == HealthStatus.OK:
            status_icon = "OK"
        elif result.status == HealthStatus.TIMEOUT:
            status_icon = "TIMEOUT"
            all_ok = False
        else:
            status_icon = "FAILED"
            all_ok = False

        print(f"  [{status_icon}] {result.name} ({result.duration_ms}ms)")
        print(f"       {result.message}")
    return all_ok


def cmd_health(_cfg: Config, args: HealthArgs) -> None:
    """Check configuration and optionally connectivity."""
    # Always run Tier 1 (config checks)
    print("\nChecking configuration...\n")
    config_results = run_config_checks()
    config_ok = _print_health_results(config_results, "Configuration")

    # Optionally run Tier 2 (connectivity checks)
    conn_ok = True
    if args.full:
        print("\nChecking connectivity...\n")
        conn_results = run_health_checks_sync(
            include_playwright=args.playwright,
            timeout_seconds=args.timeout,
        )
        conn_ok = _print_health_results(conn_results, "Connectivity")

    print()
    if config_ok and conn_ok:
        print("All checks passed.")
    else:
        if not config_ok:
            print("Some configuration checks failed. Check environment variables.")
        if not conn_ok:
            print("Some connectivity checks failed. Try restarting Claude Code if MCP tools are unresponsive.")
        sys.exit(1)


# --- Main Entry Point ---


def main() -> None:
    """Main entry point."""
    args = tyro.cli(
        Args,
        prog="jira-agent",
        description="CLI tool that fetches Jira tickets and uses Claude to implement code changes.",
    )
    cfg = Config.from_env()

    # Dispatch to appropriate handler based on args type
    match args:
        case RunArgs():
            cmd_run(cfg, args)
        case CleanupArgs():
            cmd_cleanup(cfg, args)
        case TicketArgs():
            cmd_ticket(cfg, args)
        case ContextShowArgs():
            cmd_context_show(cfg, args)
        case ContextGenerateArgs():
            cmd_context_generate(cfg, args)
        case ContextPathArgs():
            cmd_context_path(cfg, args)
        case HealthArgs():
            cmd_health(cfg, args)
        case _:
            sys.exit(f"Unknown command type: {type(args)}")


if __name__ == "__main__":
    main()
