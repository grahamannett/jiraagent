"""Claude Agent SDK health check integration.

Validates that the Claude Agent SDK is installed and the OAuth token is valid.

Run directly to test: uv run python -m jira_agent.integrations.claude.claude_sdk
"""

import asyncio
import sys
import time
from typing import Any

from jira_agent.integrations.base import (
    HealthCheckResult,
    HealthCheckTier,
    HealthStatus,
    Integration,
)


class ClaudeSDK(Integration):
    """Claude Agent SDK health check integration.

    Verifies that the Claude Agent SDK is installed and the OAuth token is valid.
    This is not an MCP integration - it checks the SDK itself which powers MCP queries.
    """

    name = "Claude Agent SDK"

    def check_config(self) -> HealthCheckResult:
        """Tier 1: Check that claude_agent_sdk is importable.

        Returns:
            HealthCheckResult with status and details.
        """
        try:
            import claude_agent_sdk  # noqa: F401

            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.OK,
                message="SDK installed",
                duration_ms=0,
                tier=HealthCheckTier.CONFIG,
            )
        except ImportError:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.FAILED,
                message="claude_agent_sdk not installed. Run: uv add claude-agent-sdk",
                duration_ms=0,
                tier=HealthCheckTier.CONFIG,
            )

    async def check_health(self) -> HealthCheckResult:
        """Tier 2: Verify OAuth token by making a minimal SDK query.

        Makes a simple query with no tools to verify authentication works.

        Returns:
            HealthCheckResult with status and details.
        """
        config_result = self.check_config()
        if config_result.status != HealthStatus.OK:
            return config_result

        start = time.monotonic()

        try:
            from claude_agent_sdk import (
                ClaudeAgentOptions,
                ResultMessage,
                query,
            )

            options = ClaudeAgentOptions(
                allowed_tools=[],
                max_turns=1,
                permission_mode="bypassPermissions",
            )

            result: HealthCheckResult | None = None

            async for message in query(
                prompt="Reply with exactly: OK",
                options=options,
            ):
                if isinstance(message, ResultMessage):
                    duration = int((time.monotonic() - start) * 1000)
                    if message.is_error:
                        error_text = str(message.result)
                        if "authentication" in error_text.lower() or "401" in error_text:
                            result = HealthCheckResult(
                                name=self.name,
                                status=HealthStatus.FAILED,
                                message="OAuth token expired. Run `/login` to re-authenticate",
                                duration_ms=duration,
                                tier=HealthCheckTier.CONNECTIVITY,
                            )
                        else:
                            result = HealthCheckResult(
                                name=self.name,
                                status=HealthStatus.FAILED,
                                message=f"Query failed: {message.result}",
                                duration_ms=duration,
                                tier=HealthCheckTier.CONNECTIVITY,
                            )
                    else:
                        result = HealthCheckResult(
                            name=self.name,
                            status=HealthStatus.OK,
                            message="OAuth token valid",
                            duration_ms=duration,
                            tier=HealthCheckTier.CONNECTIVITY,
                        )
                    break

            if result:
                return result

            duration = int((time.monotonic() - start) * 1000)
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.FAILED,
                message="Query completed without result",
                duration_ms=duration,
                tier=HealthCheckTier.CONNECTIVITY,
            )

        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            error_str = str(e).lower()

            if "authentication" in error_str or "401" in error_str or "unauthorized" in error_str:
                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.FAILED,
                    message="OAuth token expired. Run `/login` to re-authenticate",
                    duration_ms=duration,
                    tier=HealthCheckTier.CONNECTIVITY,
                )

            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.FAILED,
                message=f"Exception: {type(e).__name__}: {e}",
                duration_ms=duration,
                tier=HealthCheckTier.CONNECTIVITY,
            )

    def get_mcp_config(self) -> dict[str, Any] | None:
        """Return MCP server config for agent, or None if not MCP-based.

        ClaudeSDK is not an MCP integration, so returns None.

        Returns:
            None (this is not an MCP integration).
        """
        return None


# Standalone test mode
if __name__ == "__main__":

    async def main() -> None:
        print("Claude Agent SDK Health Check")
        print("=" * 50)

        sdk = ClaudeSDK()

        # Check config
        print("\nChecking configuration...")
        config_result = sdk.check_config()
        status_icon = "OK" if config_result.status == HealthStatus.OK else "FAILED"
        print(f"  [{status_icon}] {config_result.name} ({config_result.duration_ms}ms)")
        print(f"      {config_result.message}")

        if config_result.status != HealthStatus.OK:
            sys.exit(1)

        # Check health (OAuth token)
        print("\nChecking connectivity (OAuth token)...")
        health_result = await sdk.check_health()
        status_icon = "OK" if health_result.status == HealthStatus.OK else "FAILED"
        print(f"  [{status_icon}] {health_result.name} ({health_result.duration_ms}ms)")
        print(f"      {health_result.message}")

        sys.exit(0 if health_result.status == HealthStatus.OK else 1)

    asyncio.run(main())
