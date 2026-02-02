"""Hooks for jira-agent.

Hooks allow intercepting and modifying agent behavior at various points
during execution. They can be used for:

- Audit logging (tracking tool calls)
- Security (blocking dangerous operations)
- Metrics (measuring performance)
"""

from jira_agent.hooks.audit import AuditEntry, AuditLogger, make_audit_hook
from jira_agent.hooks.security import (
    BLOCKED_COMMAND_PATTERNS,
    BLOCKED_PATH_PATTERNS,
    SecurityViolation,
    check_tool_security,
    is_command_blocked,
    is_path_blocked,
    make_security_hook,
)

__all__ = [
    # Audit
    "AuditEntry",
    "AuditLogger",
    "make_audit_hook",
    # Security
    "BLOCKED_COMMAND_PATTERNS",
    "BLOCKED_PATH_PATTERNS",
    "SecurityViolation",
    "check_tool_security",
    "is_command_blocked",
    "is_path_blocked",
    "make_security_hook",
]
