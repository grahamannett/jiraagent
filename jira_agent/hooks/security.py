"""Security hook for blocking dangerous operations.

Prevents the agent from modifying sensitive paths or running dangerous commands.
"""

import re
from typing import Any


class SecurityViolation(Exception):
    """Raised when a security violation is detected."""

    pass


# Paths that should never be modified
BLOCKED_PATH_PATTERNS = [
    r"\.git(/|$)",  # .git directory
    r"\.env($|\.)",  # .env files
    r"node_modules(/|$)",  # node_modules directory
    r"\.ssh(/|$)",  # SSH keys
    r"\.aws(/|$)",  # AWS credentials
    r"\.gnupg(/|$)",  # GPG keys
    r"__pycache__(/|$)",  # Python cache
    r"\.venv(/|$)",  # Virtual environment
    r"venv(/|$)",  # Virtual environment
]

# Compiled patterns for efficiency
_PATH_PATTERNS = [re.compile(p) for p in BLOCKED_PATH_PATTERNS]

# Dangerous command patterns
BLOCKED_COMMAND_PATTERNS = [
    # Destructive file operations
    r"rm\s+-rf\s+/(?!\S)",  # rm -rf / (root)
    r"rm\s+-rf\s+~",  # rm -rf ~ (home)
    r"rm\s+-rf\s+\*",  # rm -rf * (wildcard)
    r"rm\s+-rf\s+\.\.",  # rm -rf .. (parent)
    # Privilege escalation
    r"\bsudo\b",  # sudo commands
    r"\bsu\b\s+",  # su commands
    r"\bdoas\b",  # doas commands
    # Dangerous permissions
    r"chmod\s+777",  # world-writable
    r"chmod\s+-R\s+777",  # recursive world-writable
    r"chown\s+-R",  # recursive ownership change
    # System modification
    r">\s*/dev/sd",  # writing to block devices
    r"dd\s+.*of=/dev/",  # dd to devices
    r"mkfs\.",  # filesystem creation
    # Network exfiltration indicators
    r"curl\s+.*\|\s*bash",  # curl pipe to bash
    r"wget\s+.*\|\s*bash",  # wget pipe to bash
    r"curl\s+.*\|\s*sh",  # curl pipe to sh
    r"wget\s+.*\|\s*sh",  # wget pipe to sh
    # Git config manipulation
    r"git\s+config\s+--global",  # global git config
    # Force operations
    r"git\s+push\s+.*--force",  # force push
    r"git\s+push\s+-f",  # force push short
    r"git\s+reset\s+--hard",  # hard reset
    # History rewriting
    r"git\s+rebase\s+-i",  # interactive rebase
    r"git\s+filter-branch",  # history rewriting
]

# Compiled command patterns
_COMMAND_PATTERNS = [re.compile(p, re.IGNORECASE) for p in BLOCKED_COMMAND_PATTERNS]


def is_path_blocked(path: str) -> tuple[bool, str | None]:
    """Check if a path is blocked for modification.

    Args:
        path: The file path to check.

    Returns:
        Tuple of (is_blocked, reason). If not blocked, reason is None.
    """
    if not path:
        return False, None

    for pattern in _PATH_PATTERNS:
        if pattern.search(path):
            return True, f"Path matches blocked pattern: {pattern.pattern}"

    return False, None


def is_command_blocked(command: str) -> tuple[bool, str | None]:
    """Check if a bash command is blocked.

    Args:
        command: The command string to check.

    Returns:
        Tuple of (is_blocked, reason). If not blocked, reason is None.
    """
    if not command:
        return False, None

    for pattern in _COMMAND_PATTERNS:
        if pattern.search(command):
            return True, f"Command matches blocked pattern: {pattern.pattern}"

    return False, None


def check_tool_security(tool_name: str, tool_input: dict[str, Any]) -> tuple[bool, str | None]:
    """Check if a tool call is allowed.

    Args:
        tool_name: Name of the tool being called.
        tool_input: Arguments to the tool.

    Returns:
        Tuple of (is_allowed, error_message). If allowed, error_message is None.
    """
    # Check file operations
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        file_path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
        blocked, reason = is_path_blocked(file_path)
        if blocked:
            return False, f"Blocked file operation on {file_path}: {reason}"

    # Check bash commands
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        blocked, reason = is_command_blocked(command)
        if blocked:
            return False, f"Blocked command: {reason}"

    return True, None


def make_security_hook():
    """Create a PreToolUse hook for security checks.

    Returns:
        An async hook function that blocks dangerous operations.
    """

    async def security_hook(
        input_data: dict[str, Any], tool_use_id: str, _context: Any
    ) -> dict[str, Any]:
        """PreToolUse hook that blocks dangerous operations.

        If a dangerous operation is detected, returns an error result
        that prevents the tool from executing.
        """
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        allowed, error = check_tool_security(tool_name, tool_input)

        if not allowed:
            # Return error to block the operation
            # The SDK will see this as a hook-provided result
            return {
                "error": True,
                "result": f"Security violation: {error}",
            }

        # Allow the operation
        return {}

    return security_hook


# Export commonly used functions
__all__ = [
    "SecurityViolation",
    "BLOCKED_PATH_PATTERNS",
    "BLOCKED_COMMAND_PATTERNS",
    "is_path_blocked",
    "is_command_blocked",
    "check_tool_security",
    "make_security_hook",
]
