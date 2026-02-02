"""Input validation for jira-agent CLI.

Validates inputs early to fail fast with clear error messages.
"""

import os
import re
import subprocess
from pathlib import Path

# Ticket key pattern: PROJECT-123 format
# Allows uppercase letters and digits in project prefix
TICKET_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")

# Required environment variables for operation
REQUIRED_ENV_VARS = [
    "JIRA_URL",
    "JIRA_USERNAME",
    "JIRA_API_TOKEN",
]


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


def validate_ticket_key(key: str) -> None:
    """Validate ticket key format.

    Args:
        key: Ticket key to validate (e.g., "SPE-123", "PROJ-1")

    Raises:
        ValidationError: If the key format is invalid.

    Examples:
        >>> validate_ticket_key("SPE-123")  # OK
        >>> validate_ticket_key("PROJECT-1")  # OK
        >>> validate_ticket_key("ABC123-456")  # OK
        >>> validate_ticket_key("spe-123")  # Raises ValidationError
        >>> validate_ticket_key("SPE123")  # Raises ValidationError
    """
    if not key:
        raise ValidationError("Ticket key cannot be empty")

    if not TICKET_KEY_PATTERN.match(key):
        raise ValidationError(
            f"Invalid ticket key format: '{key}'. "
            f"Expected format: PROJECT-123 (uppercase letters, hyphen, number)"
        )


def validate_env_vars() -> None:
    """Validate that required environment variables are set.

    Raises:
        ValidationError: If any required env var is missing or empty.
    """
    missing = []
    for var in REQUIRED_ENV_VARS:
        value = os.environ.get(var, "").strip()
        if not value:
            missing.append(var)

    if missing:
        raise ValidationError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Set these in mise.local.toml or export them directly."
        )


def validate_git_state(repo: Path) -> None:
    """Validate git repository state.

    Checks that the working directory is clean (no uncommitted changes).
    This is important before creating worktrees or branches.

    Args:
        repo: Path to the git repository.

    Raises:
        ValidationError: If there are uncommitted changes.
    """
    if not repo.exists():
        raise ValidationError(f"Repository path does not exist: {repo}")

    git_dir = repo / ".git"
    if not git_dir.exists():
        raise ValidationError(f"Not a git repository: {repo}")

    # Check for uncommitted changes
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise ValidationError(f"Failed to check git status: {result.stderr}")

    if result.stdout.strip():
        # There are uncommitted changes
        lines = result.stdout.strip().split("\n")
        file_count = len(lines)
        preview = lines[:3]
        if file_count > 3:
            preview.append(f"... and {file_count - 3} more files")

        raise ValidationError(
            f"Uncommitted changes in repository. "
            f"Please commit or stash before continuing.\n"
            f"Changed files:\n  " + "\n  ".join(preview)
        )


def validate_repo_path(path: Path) -> None:
    """Validate that the repository path exists and is a git repo.

    Args:
        path: Path to validate.

    Raises:
        ValidationError: If path doesn't exist or isn't a git repo.
    """
    if not path.exists():
        raise ValidationError(f"Repository path does not exist: {path}")

    if not path.is_dir():
        raise ValidationError(f"Repository path is not a directory: {path}")

    git_dir = path / ".git"
    if not git_dir.exists():
        raise ValidationError(f"Not a git repository: {path}")
