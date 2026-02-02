"""Jira integration via MCP (Atlassian MCP server).

Run directly to test: uv run python -m jira_agent.integrations.jira.jira_mcp [TICKET-KEY]
"""

import asyncio
import os
import sys
from typing import Any

from jira_agent.integrations.base import (
    HealthCheckResult,
    HealthStatus,
    MCPIntegration,
)


class JiraMCP(MCPIntegration):
    """Jira integration via Atlassian MCP server.

    Uses Docker to run the Atlassian MCP server which provides access to
    Jira APIs through the Claude Agent SDK.
    """

    name = "Jira MCP"

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        api_token: str | None = None,
    ) -> None:
        """Initialize Jira MCP integration.

        Args:
            url: Jira instance URL (default: JIRA_URL env var)
            username: Jira username/email (default: JIRA_USERNAME env var)
            api_token: Jira API token (default: JIRA_API_TOKEN env var)
        """
        self.url = url or os.environ.get("JIRA_URL", "")
        self.username = username or os.environ.get("JIRA_USERNAME", "")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN", "")

    def get_mcp_config(self) -> dict[str, Any]:
        """Return MCP server configuration for the agent.

        Returns:
            Dict with MCP server configuration for Atlassian.
        """
        return {
            "atlassian": {
                "command": "docker",
                "args": [
                    "run",
                    "-i",
                    "--rm",
                    "-e",
                    "JIRA_URL",
                    "-e",
                    "JIRA_USERNAME",
                    "-e",
                    "JIRA_API_TOKEN",
                    "ghcr.io/sooperset/mcp-atlassian:latest",
                ],
                "env": {
                    "JIRA_URL": self.url,
                    "JIRA_USERNAME": self.username,
                    "JIRA_API_TOKEN": self.api_token,
                },
            }
        }

    def get_tools(self) -> list[str]:
        """Return list of MCP tool names this integration provides.

        Returns:
            List of Atlassian MCP tool names.
        """
        return [
            "mcp__atlassian__getJiraIssue",
            "mcp__atlassian__getAccessibleAtlassianResources",
            "mcp__atlassian__searchJiraIssuesUsingJql",
            "mcp__atlassian__getJiraIssueComments",
        ]

    def check_config(self) -> HealthCheckResult:
        """Tier 1: Check configuration (env vars, imports). No network calls.

        Returns:
            HealthCheckResult with status and details.
        """
        # Check required env vars
        missing = []
        if not self.url:
            missing.append("JIRA_URL")
        if not self.username:
            missing.append("JIRA_USERNAME")
        if not self.api_token:
            missing.append("JIRA_API_TOKEN")

        if missing:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.FAILED,
                message=f"Missing: {', '.join(missing)}",
                duration_ms=0,
            )

        # Check SDK import (use base class helper)
        sdk_result = self._check_sdk_available()
        if sdk_result:
            return sdk_result

        return HealthCheckResult(
            name=self.name,
            status=HealthStatus.OK,
            message="Configuration valid",
            duration_ms=0,
        )

    def _get_health_check_prompt(self) -> str:
        """Return the prompt to use for MCP health check."""
        return "List accessible Atlassian resources using getAccessibleAtlassianResources."

    def _get_health_check_tools(self) -> list[str]:
        """Return the allowed tools for health check query."""
        return ["mcp__atlassian__getAccessibleAtlassianResources"]

    # check_health() is inherited from MCPIntegration
    # Uses default max_turns=3 from base class

    async def fetch_ticket(self, ticket_key: str) -> dict[str, Any] | None:
        """Fetch a Jira ticket using MCP.

        Args:
            ticket_key: The Jira ticket key (e.g., SPE-123)

        Returns:
            Dict with ticket data or None if failed.
        """
        try:
            from claude_agent_sdk import (
                AssistantMessage,
                ClaudeAgentOptions,
                ResultMessage,
                TextBlock,
                query,
            )

            prompt = f"Fetch the Jira ticket {ticket_key} and return its key, summary, status, and description."

            options = ClaudeAgentOptions(
                mcp_servers=self.get_mcp_config(),
                allowed_tools=["mcp__atlassian__getJiraIssue"],
                max_turns=5,
                permission_mode="bypassPermissions",
            )

            result_text = ""
            fetch_result: dict[str, Any] | None = None

            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            result_text = block.text

                elif isinstance(message, ResultMessage):
                    if not message.is_error and result_text:
                        fetch_result = {"ticket_key": ticket_key, "response": result_text}
                    break  # Exit loop properly to allow generator cleanup

            return fetch_result

        except Exception:
            return None


# Standalone test mode
if __name__ == "__main__":

    async def main() -> None:
        print("Jira MCP Integration Test")
        print("=" * 50)

        mcp = JiraMCP()

        # Check health
        print("\nChecking health...")
        result = await mcp.check_health()
        print(f"{result.name}: {result.status.value} ({result.duration_ms}ms)")
        print(f"  {result.message}")

        # Optionally fetch a ticket
        if len(sys.argv) > 1:
            ticket_key = sys.argv[1].upper()
            print(f"\nFetching ticket {ticket_key}...")
            ticket_data = await mcp.fetch_ticket(ticket_key)
            if ticket_data:
                print(f"  Response: {ticket_data.get('response', '')[:200]}...")
            else:
                print("  Failed to fetch ticket")

        sys.exit(0 if result.status == HealthStatus.OK else 1)

    asyncio.run(main())
