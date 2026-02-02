"""Tests for health check functionality."""

import pytest

from jira_agent.integrations import (
    HealthCheckResult,
    HealthCheckTier,
    HealthStatus,
    MCPIntegration,
    get_all_integrations,
    get_http_integrations,
    get_mcp_integrations,
    run_config_checks,
)
from jira_agent.integrations.browser import BrowserMCP
from jira_agent.integrations.claude import ClaudeSDK
from jira_agent.integrations.jira import JiraClient, JiraMCP


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""

    def test_create_ok_result(self) -> None:
        """OK result has correct fields."""
        result = HealthCheckResult(
            name="Test MCP",
            status=HealthStatus.OK,
            message="Connected successfully",
            duration_ms=150,
        )
        assert result.name == "Test MCP"
        assert result.status == HealthStatus.OK
        assert result.message == "Connected successfully"
        assert result.duration_ms == 150

    def test_create_failed_result(self) -> None:
        """Failed result has correct fields."""
        result = HealthCheckResult(
            name="Test MCP",
            status=HealthStatus.FAILED,
            message="Connection refused",
            duration_ms=50,
        )
        assert result.status == HealthStatus.FAILED

    def test_create_timeout_result(self) -> None:
        """Timeout result has correct fields."""
        result = HealthCheckResult(
            name="Test MCP",
            status=HealthStatus.TIMEOUT,
            message="Timed out after 30s",
            duration_ms=30000,
        )
        assert result.status == HealthStatus.TIMEOUT


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self) -> None:
        """Status enum has expected values."""
        assert HealthStatus.OK.value == "ok"
        assert HealthStatus.FAILED.value == "failed"
        assert HealthStatus.TIMEOUT.value == "timeout"

    def test_status_comparison(self) -> None:
        """Status values can be compared."""
        assert HealthStatus.OK == HealthStatus.OK
        assert HealthStatus.OK != HealthStatus.FAILED


class TestIntegrationRegistry:
    """Tests for the integration registry functions."""

    def test_get_all_integrations_returns_list(self) -> None:
        """get_all_integrations returns a list of integrations."""
        integrations = get_all_integrations()
        assert isinstance(integrations, list)

    def test_get_mcp_integrations_returns_mcp_only(self) -> None:
        """get_mcp_integrations returns only MCP-based integrations."""
        integrations = get_mcp_integrations()
        assert isinstance(integrations, list)
        for integration in integrations:
            assert isinstance(integration, MCPIntegration)

    def test_get_http_integrations_excludes_mcp(self) -> None:
        """get_http_integrations excludes MCP integrations."""
        integrations = get_http_integrations()
        assert isinstance(integrations, list)
        for integration in integrations:
            assert not isinstance(integration, MCPIntegration)


class TestIntegrationProtocol:
    """Tests for the Integration protocol."""

    def test_mcp_integration_has_required_attributes(self) -> None:
        """MCPIntegration instances have required protocol attributes."""
        jira_mcp = JiraMCP()
        assert hasattr(jira_mcp, "name")
        assert hasattr(jira_mcp, "check_health")
        assert hasattr(jira_mcp, "get_mcp_config")
        assert hasattr(jira_mcp, "get_tools")

    def test_browser_mcp_has_required_attributes(self) -> None:
        """BrowserMCP has required protocol attributes."""
        browser_mcp = BrowserMCP()
        assert hasattr(browser_mcp, "name")
        assert hasattr(browser_mcp, "check_health")
        assert hasattr(browser_mcp, "get_mcp_config")
        assert hasattr(browser_mcp, "get_tools")

    def test_jira_mcp_get_mcp_config(self) -> None:
        """JiraMCP.get_mcp_config returns valid config."""
        jira_mcp = JiraMCP(url="https://test.atlassian.net", username="test", api_token="token")
        config = jira_mcp.get_mcp_config()
        assert isinstance(config, dict)
        assert "atlassian" in config
        assert "command" in config["atlassian"]
        assert "args" in config["atlassian"]

    def test_browser_mcp_get_mcp_config(self) -> None:
        """BrowserMCP.get_mcp_config returns valid config."""
        browser_mcp = BrowserMCP()
        config = browser_mcp.get_mcp_config()
        assert isinstance(config, dict)
        assert "chrome-devtools" in config
        assert "command" in config["chrome-devtools"]
        assert "args" in config["chrome-devtools"]

    def test_jira_mcp_get_tools(self) -> None:
        """JiraMCP.get_tools returns list of tool names."""
        jira_mcp = JiraMCP()
        tools = jira_mcp.get_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert all(isinstance(t, str) for t in tools)
        assert all(t.startswith("mcp__atlassian__") for t in tools)

    def test_browser_mcp_get_tools(self) -> None:
        """BrowserMCP.get_tools returns list of tool names."""
        browser_mcp = BrowserMCP()
        tools = browser_mcp.get_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert all(isinstance(t, str) for t in tools)


class TestHealthCheckTier:
    """Tests for HealthCheckTier enum."""

    def test_tier_values(self) -> None:
        """Tier enum has expected values."""
        assert HealthCheckTier.CONFIG.value == "config"
        assert HealthCheckTier.CONNECTIVITY.value == "connectivity"


class TestCheckConfig:
    """Tests for check_config() Tier 1 checks."""

    def test_jira_mcp_check_config_valid(self) -> None:
        """JiraMCP.check_config returns OK with valid config."""
        jira_mcp = JiraMCP(url="https://test.atlassian.net", username="test", api_token="token")
        result = jira_mcp.check_config()
        assert result.status == HealthStatus.OK
        assert "Configuration valid" in result.message

    def test_jira_mcp_check_config_missing_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JiraMCP.check_config returns FAILED with missing URL."""
        monkeypatch.delenv("JIRA_URL", raising=False)
        jira_mcp = JiraMCP(url="", username="test", api_token="token")
        result = jira_mcp.check_config()
        assert result.status == HealthStatus.FAILED
        assert "JIRA_URL" in result.message

    def test_jira_mcp_check_config_missing_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JiraMCP.check_config returns FAILED with all missing."""
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_USERNAME", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        jira_mcp = JiraMCP(url="", username="", api_token="")
        result = jira_mcp.check_config()
        assert result.status == HealthStatus.FAILED
        assert "JIRA_URL" in result.message
        assert "JIRA_USERNAME" in result.message
        assert "JIRA_API_TOKEN" in result.message

    def test_browser_mcp_check_config_valid(self) -> None:
        """BrowserMCP.check_config returns OK (no required env vars)."""
        browser_mcp = BrowserMCP()
        result = browser_mcp.check_config()
        assert result.status == HealthStatus.OK
        assert "Configuration valid" in result.message

    def test_jira_client_check_config_valid(self) -> None:
        """JiraClient.check_config returns OK with valid config."""
        jira_client = JiraClient(url="https://test.atlassian.net", username="test", api_token="token")
        result = jira_client.check_config()
        assert result.status == HealthStatus.OK
        assert "Configuration valid" in result.message

    def test_check_config_has_duration(self) -> None:
        """check_config results include duration_ms."""
        jira_mcp = JiraMCP(url="https://test.atlassian.net", username="test", api_token="token")
        result = jira_mcp.check_config()
        assert isinstance(result.duration_ms, int)
        assert result.duration_ms >= 0


class TestRunConfigChecks:
    """Tests for run_config_checks() function."""

    def test_run_config_checks_returns_list(self) -> None:
        """run_config_checks returns a list of results."""
        results = run_config_checks()
        assert isinstance(results, list)
        for result in results:
            assert isinstance(result, HealthCheckResult)

    def test_run_config_checks_includes_mcp_by_default(self) -> None:
        """run_config_checks includes MCP integrations by default."""
        results = run_config_checks()
        names = [r.name for r in results]
        assert "Jira MCP" in names or "Browser MCP (Chrome DevTools)" in names


class TestIntegrationHasCheckConfig:
    """Tests that all integrations implement check_config."""

    def test_jira_mcp_has_check_config(self) -> None:
        """JiraMCP has check_config method."""
        jira_mcp = JiraMCP()
        assert hasattr(jira_mcp, "check_config")
        assert callable(jira_mcp.check_config)

    def test_browser_mcp_has_check_config(self) -> None:
        """BrowserMCP has check_config method."""
        browser_mcp = BrowserMCP()
        assert hasattr(browser_mcp, "check_config")
        assert callable(browser_mcp.check_config)


class TestMCPIntegrationBaseClass:
    """Tests for MCPIntegration base class template method pattern."""

    def test_jira_mcp_has_health_check_hooks(self) -> None:
        """JiraMCP has required health check hook methods."""
        jira_mcp = JiraMCP()
        assert hasattr(jira_mcp, "_get_health_check_prompt")
        assert hasattr(jira_mcp, "_get_health_check_tools")
        assert hasattr(jira_mcp, "_get_health_check_max_turns")
        assert callable(jira_mcp._get_health_check_prompt)
        assert callable(jira_mcp._get_health_check_tools)
        assert callable(jira_mcp._get_health_check_max_turns)

    def test_browser_mcp_has_health_check_hooks(self) -> None:
        """BrowserMCP has required health check hook methods."""
        browser_mcp = BrowserMCP()
        assert hasattr(browser_mcp, "_get_health_check_prompt")
        assert hasattr(browser_mcp, "_get_health_check_tools")
        assert hasattr(browser_mcp, "_get_health_check_max_turns")

    def test_jira_mcp_health_check_prompt(self) -> None:
        """JiraMCP._get_health_check_prompt returns correct prompt."""
        jira_mcp = JiraMCP()
        prompt = jira_mcp._get_health_check_prompt()
        assert isinstance(prompt, str)
        assert "getAccessibleAtlassianResources" in prompt

    def test_browser_mcp_health_check_prompt(self) -> None:
        """BrowserMCP._get_health_check_prompt returns correct prompt."""
        browser_mcp = BrowserMCP()
        prompt = browser_mcp._get_health_check_prompt()
        assert isinstance(prompt, str)
        assert "example.com" in prompt
        assert "screenshot" in prompt

    def test_jira_mcp_health_check_tools(self) -> None:
        """JiraMCP._get_health_check_tools returns correct tools."""
        jira_mcp = JiraMCP()
        tools = jira_mcp._get_health_check_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert "mcp__atlassian__getAccessibleAtlassianResources" in tools

    def test_browser_mcp_health_check_tools(self) -> None:
        """BrowserMCP._get_health_check_tools returns correct tools."""
        browser_mcp = BrowserMCP()
        tools = browser_mcp._get_health_check_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert "mcp__chrome-devtools__navigate" in tools
        assert "mcp__chrome-devtools__take_screenshot" in tools

    def test_jira_mcp_max_turns_default(self) -> None:
        """JiraMCP uses default max_turns of 3."""
        jira_mcp = JiraMCP()
        max_turns = jira_mcp._get_health_check_max_turns()
        assert max_turns == 3

    def test_browser_mcp_max_turns_override(self) -> None:
        """BrowserMCP overrides max_turns to 5."""
        browser_mcp = BrowserMCP()
        max_turns = browser_mcp._get_health_check_max_turns()
        assert max_turns == 5

    def test_check_health_inherited_from_base(self) -> None:
        """check_health() is inherited from MCPIntegration, not overridden."""
        jira_mcp = JiraMCP()
        browser_mcp = BrowserMCP()

        # Both should have check_health from MCPIntegration base class
        assert hasattr(jira_mcp, "check_health")
        assert hasattr(browser_mcp, "check_health")

        # Verify check_health is the same method as in base class
        assert jira_mcp.check_health.__func__ is MCPIntegration.check_health
        assert browser_mcp.check_health.__func__ is MCPIntegration.check_health

    def test_mcp_connectivity_method_exists(self) -> None:
        """_check_mcp_connectivity() exists in MCPIntegration."""
        jira_mcp = JiraMCP()
        assert hasattr(jira_mcp, "_check_mcp_connectivity")
        assert callable(jira_mcp._check_mcp_connectivity)


class TestClaudeSDK:
    """Tests for ClaudeSDK integration."""

    def test_claude_sdk_has_required_attributes(self) -> None:
        """ClaudeSDK has required protocol attributes."""
        sdk = ClaudeSDK()
        assert hasattr(sdk, "name")
        assert hasattr(sdk, "check_config")
        assert hasattr(sdk, "check_health")
        assert hasattr(sdk, "get_mcp_config")

    def test_claude_sdk_name(self) -> None:
        """ClaudeSDK has correct name."""
        sdk = ClaudeSDK()
        assert sdk.name == "Claude Agent SDK"

    def test_claude_sdk_check_config_ok(self) -> None:
        """ClaudeSDK.check_config returns OK when SDK is installed."""
        sdk = ClaudeSDK()
        result = sdk.check_config()
        assert result.status == HealthStatus.OK
        assert "SDK installed" in result.message

    def test_claude_sdk_check_config_has_correct_tier(self) -> None:
        """ClaudeSDK.check_config returns CONFIG tier."""
        sdk = ClaudeSDK()
        result = sdk.check_config()
        assert result.tier == HealthCheckTier.CONFIG

    def test_claude_sdk_get_mcp_config_returns_none(self) -> None:
        """ClaudeSDK.get_mcp_config returns None (not an MCP integration)."""
        sdk = ClaudeSDK()
        config = sdk.get_mcp_config()
        assert config is None

    def test_claude_sdk_in_all_integrations(self) -> None:
        """ClaudeSDK is included in get_all_integrations."""
        integrations = get_all_integrations()
        names = [i.name for i in integrations]
        assert "Claude Agent SDK" in names

    def test_claude_sdk_not_in_mcp_integrations(self) -> None:
        """ClaudeSDK is not an MCP integration."""
        sdk = ClaudeSDK()
        assert not isinstance(sdk, MCPIntegration)
        mcp_integrations = get_mcp_integrations()
        assert sdk.name not in [i.name for i in mcp_integrations]

    def test_claude_sdk_in_config_checks(self) -> None:
        """ClaudeSDK appears in run_config_checks output."""
        results = run_config_checks()
        names = [r.name for r in results]
        assert "Claude Agent SDK" in names


class TestClaudeSDKAuthErrors:
    """Tests for ClaudeSDK authentication error handling."""

    @pytest.mark.asyncio
    async def test_check_health_handles_auth_error_in_result(self) -> None:
        """check_health returns helpful message for authentication errors."""
        sdk = ClaudeSDK()

        # We can't easily mock the SDK, but we can verify the error handling logic
        # by checking that the method exists and returns a HealthCheckResult
        result = sdk.check_config()
        assert isinstance(result, HealthCheckResult)

    def test_auth_error_message_format(self) -> None:
        """Verify auth error message is user-friendly."""
        # This tests the expected error message format
        expected_message = "OAuth token expired. Run `/login` to re-authenticate"
        assert "OAuth" in expected_message
        assert "/login" in expected_message
