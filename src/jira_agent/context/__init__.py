"""Context management for the Jira agent.

This module handles loading and generating context files that provide
AI agents with understanding of the target repository.

Context files are stored in repo-specific directories:
    {jiraagent}/contexts/{repo_name}/AGENT.md  (default)

Or override via environment variable:
    JIRA_AGENT_CONTEXTS_DIR=~/.jira-agent/contexts
"""

import os
from pathlib import Path

from jira_agent.context.generator import ContextGenerator

# Project root directory (src layout: package is under src/)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def get_default_context_dir() -> Path:
    """Get base directory for context files.

    Priority:
    1. JIRA_AGENT_CONTEXTS_DIR env var (if set)
    2. {jiraagent}/contexts/ (default)

    Returns:
        Path to the base context directory.
    """
    if env_dir := os.environ.get("JIRA_AGENT_CONTEXTS_DIR"):
        return Path(env_dir).expanduser()
    return PROJECT_ROOT / "contexts"


def get_context_path_for_repo(repo_path: Path) -> Path:
    """Get default context path for a repository.

    Args:
        repo_path: Path to the repository.

    Returns:
        Path where context file should be stored for this repo.
    """
    return get_default_context_dir() / repo_path.name / "AGENT.md"


def load_context(context_path: Path) -> str:
    """Load context from specified path.

    Args:
        context_path: Path to the context file.

    Returns:
        The context content as a string.

    Raises:
        FileNotFoundError: If context file doesn't exist.
    """
    if not context_path.exists():
        raise FileNotFoundError(
            f"Context file not found: {context_path}\nRun 'jira-agent context generate' to create it."
        )
    return context_path.read_text()


def context_exists(context_path: Path) -> bool:
    """Check if context file exists at specified path.

    Args:
        context_path: Path to check.

    Returns:
        True if context file exists.
    """
    return context_path.exists()


def generate_context(repo_path: Path, output_path: Path, deep: bool = False) -> str:
    """Generate context for a repository and save to specified path.

    Args:
        repo_path: Path to the repository to analyze.
        output_path: Path where context file will be written.
        deep: If True, use AI to expand with comprehensive details (slower).

    Returns:
        The generated context content.
    """
    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    generator = ContextGenerator()
    return generator.generate(repo_path, output_path, deep=deep)


__all__ = [
    "load_context",
    "context_exists",
    "generate_context",
    "get_default_context_dir",
    "get_context_path_for_repo",
    "ContextGenerator",
]
