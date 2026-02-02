"""Jira integrations - HTTP and MCP implementations."""

from jira_agent.integrations.jira.client import (
    JiraClient,
    Ticket,
    check_jira_connection,
    fetch_ticket,
    get_client,
)
from jira_agent.integrations.jira.jira_mcp import JiraMCP

__all__ = [
    # HTTP client
    "JiraClient",
    "Ticket",
    "check_jira_connection",
    "fetch_ticket",
    "get_client",
    # MCP integration
    "JiraMCP",
]
