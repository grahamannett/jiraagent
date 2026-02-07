"""Health checks for service connectivity using the integration registry."""

import anyio
from typing import TYPE_CHECKING

from jira_agent.integrations.base import (
    HealthCheckResult,
    HealthStatus,
    Integration,
    MCPIntegration,
)

if TYPE_CHECKING:
    pass


def get_all_integrations() -> list[Integration]:
    """Return all available integrations.

    Returns:
        List of all integration instances (both HTTP and MCP).
    """
    from jira_agent.integrations.browser import BrowserMCP
    from jira_agent.integrations.claude import ClaudeSDK
    from jira_agent.integrations.jira import JiraClient, JiraMCP

    integrations: list[Integration] = []

    # HTTP integrations - may fail if env vars not set
    try:
        integrations.append(JiraClient())
    except ValueError:
        pass  # Skip if not configured

    # MCP integrations
    integrations.append(JiraMCP())
    integrations.append(BrowserMCP())

    # SDK integrations
    integrations.append(ClaudeSDK())

    return integrations


def get_http_integrations() -> list[Integration]:
    """Return only HTTP-based integrations.

    Returns:
        List of HTTP integration instances.
    """
    return [i for i in get_all_integrations() if not isinstance(i, MCPIntegration)]


def get_mcp_integrations() -> list[MCPIntegration]:
    """Return only MCP-based integrations.

    Returns:
        List of MCP integration instances.
    """
    return [i for i in get_all_integrations() if isinstance(i, MCPIntegration)]


async def run_health_checks_async(
    include_mcp: bool = False,
) -> list[HealthCheckResult]:
    """Run health checks on integrations asynchronously.

    Args:
        include_mcp: If True, also check MCP integrations.

    Returns:
        List of health check results.
    """
    if include_mcp:
        integrations = get_all_integrations()
    else:
        integrations = get_http_integrations()

    if not integrations:
        return []

    # Run all health checks concurrently
    results = await asyncio.gather(*[i.check_health() for i in integrations])
    return list(results)


def run_health_checks(include_mcp: bool = False) -> list[HealthCheckResult]:
    """Run health checks on integrations synchronously.

    Args:
        include_mcp: If True, also check MCP integrations.

    Returns:
        List of health check results.
    """
    return anyio.run(run_health_checks_async, include_mcp)


def run_config_checks(include_mcp: bool = True) -> list[HealthCheckResult]:
    """Run Tier 1 config checks (fast, no network).

    Args:
        include_mcp: If True, include MCP integrations. Defaults to True.

    Returns:
        List of health check results.
    """
    if include_mcp:
        integrations = get_all_integrations()
    else:
        integrations = get_http_integrations()

    if not integrations:
        return []

    return [i.check_config() for i in integrations]


# Legacy function for backwards compatibility
def run_health_checks_sync(
    include_playwright: bool = False,
    timeout_seconds: int = 30,  # noqa: ARG001 - kept for API compatibility
) -> list[HealthCheckResult]:
    """Run Tier 2 connectivity checks (synchronous).

    Args:
        include_playwright: If True, include browser/playwright MCP checks.
        timeout_seconds: Ignored (kept for API compatibility).

    Returns:
        List of health check results.
    """
    return run_health_checks(include_mcp=include_playwright)


# Legacy function - delegates to JiraClient now
def check_jira() -> HealthCheckResult:
    """Check if Jira API is accessible.

    Uses direct HTTP calls to the Jira REST API.
    Requires JIRA_URL, JIRA_USERNAME, and JIRA_API_TOKEN env vars.
    """
    from jira_agent.integrations.jira import JiraClient

    try:
        client = JiraClient()
        return anyio.run(client.check_health)
    except ValueError as e:
        return HealthCheckResult(
            name="Jira HTTP",
            status=HealthStatus.FAILED,
            message=str(e),
            duration_ms=0,
        )


# Standalone test mode
if __name__ == "__main__":
    import sys

    print("Integration Health Checks")
    print("=" * 60)

    # Check if MCP should be included
    include_mcp = "--mcp" in sys.argv or "--all" in sys.argv

    print(f"\nRunning health checks (include_mcp={include_mcp})...")
    print("-" * 60)

    results = run_health_checks(include_mcp=include_mcp)

    if not results:
        print("No integrations configured or available.")
        sys.exit(1)

    all_ok = True
    for result in results:
        status_icon = "✓" if result.status == HealthStatus.OK else "✗"
        print(f"  [{status_icon}] {result.name} ({result.duration_ms}ms)")
        print(f"      {result.message}")
        if result.status != HealthStatus.OK:
            all_ok = False

    print("-" * 60)
    if all_ok:
        print("All checks passed.")
    else:
        print("Some checks failed.")

    sys.exit(0 if all_ok else 1)
