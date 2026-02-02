"""Base classes for integrations."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class HealthStatus(Enum):
    """Health check status."""

    OK = "ok"
    FAILED = "failed"
    TIMEOUT = "timeout"


class HealthCheckTier(Enum):
    """Health check tier."""

    CONFIG = "config"  # Tier 1: fast, no network
    CONNECTIVITY = "connectivity"  # Tier 2: slow, network calls


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    name: str
    status: HealthStatus
    message: str
    duration_ms: int
    tier: HealthCheckTier = HealthCheckTier.CONFIG


class Integration(ABC):
    """Abstract base class for all integrations.

    All integrations must provide:
    - name: Human-readable name (e.g., "Jira HTTP", "Jira MCP")
    - check_config(): Sync method to validate configuration (Tier 1, no network)
    - check_health(): Async method to verify connectivity (Tier 2, network calls)
    - get_mcp_config(): Returns MCP server config for agent, or None if not MCP-based
    """

    name: str

    @abstractmethod
    def check_config(self) -> HealthCheckResult:
        """Tier 1: Check configuration (env vars, imports). No network calls.

        Returns:
            HealthCheckResult with status and details.
        """
        ...

    @abstractmethod
    async def check_health(self) -> HealthCheckResult:
        """Tier 2: Check connectivity. May make network calls.

        Returns:
            HealthCheckResult with status and details.
        """
        ...

    @abstractmethod
    def get_mcp_config(self) -> dict[str, Any] | None:
        """Return MCP server config for agent, or None if not MCP-based.

        Returns:
            Dict with MCP server configuration, or None for HTTP-based integrations.
        """
        ...


class MCPIntegration(Integration):
    """Base class for MCP-based integrations.

    Provides common functionality for MCP integrations including:
    - SDK availability check helper
    - MCP config generation
    - Shared health check implementation via template method

    Subclasses must implement:
    - check_config()
    - get_mcp_config()
    - get_tools()
    - _get_health_check_prompt()
    - _get_health_check_tools()

    Subclasses may override:
    - _get_health_check_max_turns() (default: 3)
    """

    name: str = "MCP Integration"

    def _check_sdk_available(self) -> HealthCheckResult | None:
        """Check if claude_agent_sdk is available.

        Returns:
            HealthCheckResult with FAILED status if SDK not installed, None if OK.
        """
        try:
            import claude_agent_sdk  # noqa: F401

            return None  # SDK available
        except ImportError:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.FAILED,
                message="claude_agent_sdk not installed",
                duration_ms=0,
                tier=HealthCheckTier.CONFIG,
            )

    @abstractmethod
    def get_tools(self) -> list[str]:
        """Return list of MCP tool names this integration provides.

        Returns:
            List of tool names (e.g., ["mcp__atlassian__getJiraIssue"]).
        """
        ...

    @abstractmethod
    def _get_health_check_prompt(self) -> str:
        """Return the prompt to use for MCP health check.

        Returns:
            Prompt string for the health check query.
        """
        ...

    @abstractmethod
    def _get_health_check_tools(self) -> list[str]:
        """Return the allowed tools for health check query.

        Returns:
            List of tool names allowed during health check.
        """
        ...

    def _get_health_check_max_turns(self) -> int:
        """Return max turns for health check query.

        Override to customize. Default is 3.

        Returns:
            Maximum number of turns for the health check query.
        """
        return 3

    async def check_health(self) -> HealthCheckResult:
        """Tier 2: Check MCP connectivity.

        Runs config check first, then attempts MCP query.
        Subclasses customize via _get_health_check_prompt() and _get_health_check_tools().

        Returns:
            HealthCheckResult with status and details.
        """
        config_result = self.check_config()
        if config_result.status != HealthStatus.OK:
            return config_result

        return await self._check_mcp_connectivity()

    async def _check_mcp_connectivity(self) -> HealthCheckResult:
        """Execute MCP connectivity check using SDK query.

        Returns:
            HealthCheckResult with status and details.
        """
        start = time.monotonic()

        try:
            from claude_agent_sdk import (
                ClaudeAgentOptions,
                ResultMessage,
                SystemMessage,
                query,
            )

            options = ClaudeAgentOptions(
                mcp_servers=self.get_mcp_config(),
                allowed_tools=self._get_health_check_tools(),
                max_turns=self._get_health_check_max_turns(),
                permission_mode="bypassPermissions",
            )

            mcp_connected = False
            mcp_error: str | None = None
            result: HealthCheckResult | None = None

            async for message in query(
                prompt=self._get_health_check_prompt(),
                options=options,
            ):
                if isinstance(message, SystemMessage):
                    if hasattr(message, "mcp_servers") and message.mcp_servers:
                        for server in message.mcp_servers:
                            status = getattr(server, "status", "unknown")
                            if status == "connected":
                                mcp_connected = True
                            else:
                                mcp_error = getattr(
                                    server, "error", f"Status: {status}"
                                )

                elif isinstance(message, ResultMessage):
                    duration = int((time.monotonic() - start) * 1000)
                    if message.is_error:
                        result = HealthCheckResult(
                            name=self.name,
                            status=HealthStatus.FAILED,
                            message=f"Query failed: {message.result}",
                            duration_ms=duration,
                            tier=HealthCheckTier.CONNECTIVITY,
                        )
                    elif mcp_connected:
                        result = HealthCheckResult(
                            name=self.name,
                            status=HealthStatus.OK,
                            message="MCP server connected and responding",
                            duration_ms=duration,
                            tier=HealthCheckTier.CONNECTIVITY,
                        )
                    break  # Exit loop properly to allow generator cleanup

            if result:
                return result

            duration = int((time.monotonic() - start) * 1000)

            if mcp_error:
                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.FAILED,
                    message=f"MCP server error: {mcp_error}",
                    duration_ms=duration,
                    tier=HealthCheckTier.CONNECTIVITY,
                )

            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.FAILED,
                message="MCP query completed without result",
                duration_ms=duration,
                tier=HealthCheckTier.CONNECTIVITY,
            )

        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.FAILED,
                message=f"Exception: {type(e).__name__}: {e}",
                duration_ms=duration,
                tier=HealthCheckTier.CONNECTIVITY,
            )


class HTTPIntegration(Integration):
    """Base class for HTTP-based integrations.

    Provides concrete implementation of get_mcp_config() (returns None).

    Subclasses must implement:
    - check_config()
    - check_health()
    """

    name: str = "HTTP Integration"

    def get_mcp_config(self) -> None:
        """HTTP integrations don't have MCP configs.

        Returns:
            None (HTTP integrations don't use MCP).
        """
        return None
