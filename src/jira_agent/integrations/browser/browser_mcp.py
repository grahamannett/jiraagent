"""Browser automation via Chrome DevTools MCP.

Run directly to test: uv run python -m jira_agent.integrations.browser.browser_mcp
"""

import asyncio
import sys
from typing import Any

from jira_agent.integrations.base import (
    HealthCheckResult,
    HealthStatus,
    MCPIntegration,
)


class BrowserMCP(MCPIntegration):
    """Browser automation via Chrome DevTools MCP server.

    Uses npx to run the Chrome DevTools MCP server which provides access to
    browser automation through the Claude Agent SDK.
    """

    name = "Browser MCP (Chrome DevTools)"

    def __init__(self, browser_url: str | None = None) -> None:
        """Initialize Browser MCP integration.

        Args:
            browser_url: Optional Chrome DevTools URL (e.g., http://127.0.0.1:9222)
        """
        self.browser_url = browser_url

    def get_mcp_config(self) -> dict[str, Any]:
        """Return MCP server configuration for the agent.

        Returns:
            Dict with MCP server configuration for Chrome DevTools.
        """
        args = ["-y", "chrome-devtools-mcp@latest"]
        if self.browser_url:
            args.append(f"--browser-url={self.browser_url}")

        return {
            "chrome-devtools": {
                "command": "npx",
                "args": args,
            }
        }

    def get_tools(self) -> list[str]:
        """Return list of MCP tool names this integration provides.

        Returns:
            List of Chrome DevTools MCP tool names.
        """
        return [
            "mcp__chrome-devtools__navigate",
            "mcp__chrome-devtools__take_screenshot",
            "mcp__chrome-devtools__click",
            "mcp__chrome-devtools__type",
            "mcp__chrome-devtools__get_content",
            "mcp__chrome-devtools__evaluate",
        ]

    def check_config(self) -> HealthCheckResult:
        """Tier 1: Check configuration (imports). No network calls.

        Browser MCP has no required env vars, just checks SDK is installed.

        Returns:
            HealthCheckResult with status and details.
        """
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
        return "Navigate to https://example.com and take a screenshot, saving it as /tmp/health_check.png"

    def _get_health_check_tools(self) -> list[str]:
        """Return the allowed tools for health check query."""
        return [
            "mcp__chrome-devtools__navigate",
            "mcp__chrome-devtools__take_screenshot",
        ]

    def _get_health_check_max_turns(self) -> int:
        """Return max turns for health check (browser needs more turns)."""
        return 5

    # check_health() is inherited from MCPIntegration

    async def navigate_and_screenshot(self, url: str, screenshot_path: str = "screenshot.png") -> bool:
        """Navigate to a URL and take a screenshot.

        Args:
            url: URL to navigate to
            screenshot_path: Path to save screenshot

        Returns:
            True if successful, False otherwise.
        """
        try:
            from claude_agent_sdk import (
                ClaudeAgentOptions,
                ResultMessage,
                query,
            )

            prompt = f"Navigate to {url} and take a screenshot, saving it as {screenshot_path}"

            options = ClaudeAgentOptions(
                mcp_servers=self.get_mcp_config(),
                allowed_tools=[
                    "mcp__chrome-devtools__navigate",
                    "mcp__chrome-devtools__take_screenshot",
                ],
                max_turns=5,
                permission_mode="bypassPermissions",
            )

            success = False
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    success = not message.is_error
                    break  # Exit loop properly to allow generator cleanup

            return success

        except Exception:
            return False


# Standalone test mode
if __name__ == "__main__":

    async def main() -> None:
        print("Browser MCP Integration Test")
        print("=" * 50)

        mcp = BrowserMCP()

        # Check health
        print("\nChecking health...")
        result = await mcp.check_health()
        print(f"{result.name}: {result.status.value} ({result.duration_ms}ms)")
        print(f"  {result.message}")

        # Optionally take a screenshot
        if len(sys.argv) > 1 and sys.argv[1] == "--screenshot":
            url = sys.argv[2] if len(sys.argv) > 2 else "https://example.com"
            print(f"\nNavigating to {url} and taking screenshot...")
            success = await mcp.navigate_and_screenshot(url, "screenshot.png")
            if success:
                print("  Screenshot saved to screenshot.png")
            else:
                print("  Failed to take screenshot")

        sys.exit(0 if result.status == HealthStatus.OK else 1)

    asyncio.run(main())
