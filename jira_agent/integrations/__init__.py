"""External service integrations (Jira, Browser, etc.).

This module provides a unified interface for all integrations, both HTTP and MCP-based.

Usage:
    # Get all integrations
    from jira_agent.integrations import get_all_integrations, get_mcp_integrations

    # Run health checks
    from jira_agent.integrations import run_health_checks
    results = run_health_checks(include_mcp=True)

    # Use specific integrations
    from jira_agent.integrations import JiraClient, JiraMCP, BrowserMCP

    # Get MCP configs for agent
    mcp_configs = {}
    for integration in get_mcp_integrations():
        config = integration.get_mcp_config()
        if config:
            mcp_configs.update(config)
"""

# Base classes and types
from jira_agent.integrations.base import (
    HealthCheckResult,
    HealthCheckTier,
    HealthStatus,
    HTTPIntegration,
    Integration,
    MCPIntegration,
)

# Browser integrations
from jira_agent.integrations.browser import BrowserMCP

# Health check functions
from jira_agent.integrations.health import (
    check_jira,
    get_all_integrations,
    get_http_integrations,
    get_mcp_integrations,
    run_config_checks,
    run_health_checks,
    run_health_checks_async,
    run_health_checks_sync,
)

# Jira integrations
from jira_agent.integrations.jira import (
    JiraClient,
    JiraMCP,
    Ticket,
    check_jira_connection,
    fetch_ticket,
    get_client,
)

__all__ = [
    # Base types
    "HealthCheckResult",
    "HealthCheckTier",
    "HealthStatus",
    "HTTPIntegration",
    "Integration",
    "MCPIntegration",
    # Registry functions
    "get_all_integrations",
    "get_http_integrations",
    "get_mcp_integrations",
    # Health check functions
    "check_jira",
    "run_config_checks",
    "run_health_checks",
    "run_health_checks_async",
    "run_health_checks_sync",
    # Jira
    "JiraClient",
    "JiraMCP",
    "Ticket",
    "check_jira_connection",
    "fetch_ticket",
    "get_client",
    # Browser
    "BrowserMCP",
]
