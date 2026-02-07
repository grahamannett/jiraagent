"""Jira API client using direct HTTP calls."""

import asyncio
import os
import time
from dataclasses import dataclass

import httpx

from jira_agent.integrations.base import (
    HealthCheckResult,
    HealthCheckTier,
    HealthStatus,
    HTTPIntegration,
)


@dataclass(frozen=True, slots=True)
class Ticket:
    key: str
    summary: str
    description: str
    issue_type: str
    priority: str
    status: str


class JiraClient(HTTPIntegration):
    """Client for Jira REST API."""

    name = "Jira HTTP"

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        api_token: str | None = None,
    ) -> None:
        """Initialize Jira client.

        Args:
            url: Jira instance URL (default: JIRA_URL env var)
            username: Jira username/email (default: JIRA_USERNAME env var)
            api_token: Jira API token (default: JIRA_API_TOKEN env var)
        """
        self.url = (url or os.environ.get("JIRA_URL", "")).rstrip("/")
        self.username = username or os.environ.get("JIRA_USERNAME", "")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN", "")

        if not self.url:
            raise ValueError("JIRA_URL environment variable not set")
        if not self.username:
            raise ValueError("JIRA_USERNAME environment variable not set")
        if not self.api_token:
            raise ValueError("JIRA_API_TOKEN environment variable not set")

    def _get_auth(self) -> tuple[str, str]:
        """Return basic auth tuple."""
        return (self.username, self.api_token)

    def get_issue(self, issue_key: str) -> Ticket:
        """Fetch a Jira issue by key.

        Args:
            issue_key: The issue key (e.g., SPE-123)

        Returns:
            Ticket with issue details

        Raises:
            RuntimeError: If the API call fails
        """
        api_url = f"{self.url}/rest/api/3/issue/{issue_key}"

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(api_url, auth=self._get_auth())
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise RuntimeError(f"Ticket {issue_key} not found") from e
            raise RuntimeError(f"Failed to fetch ticket {issue_key}: {e}") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Failed to connect to Jira: {e}") from e

        fields = data.get("fields", {})

        # Extract description text from Atlassian Document Format
        description = ""
        desc_data = fields.get("description")
        if desc_data:
            description = self._extract_text_from_adf(desc_data)

        return Ticket(
            key=data.get("key", issue_key),
            summary=fields.get("summary", ""),
            description=description,
            issue_type=fields.get("issuetype", {}).get("name", "Unknown"),
            priority=fields.get("priority", {}).get("name", "Unknown"),
            status=fields.get("status", {}).get("name", "Unknown"),
        )

    def _extract_text_from_adf(self, adf: dict) -> str:
        """Extract plain text from Atlassian Document Format.

        Args:
            adf: The ADF document structure

        Returns:
            Plain text representation
        """
        if not isinstance(adf, dict):
            return str(adf) if adf else ""

        text_parts: list[str] = []

        def extract_recursive(node: dict | list | str) -> None:
            if isinstance(node, str):
                text_parts.append(node)
            elif isinstance(node, list):
                for item in node:
                    extract_recursive(item)
            elif isinstance(node, dict):
                # Handle text nodes
                if node.get("type") == "text":
                    text_parts.append(node.get("text", ""))
                # Handle hard breaks
                elif node.get("type") == "hardBreak":
                    text_parts.append("\n")
                # Handle paragraphs - add newline after
                elif node.get("type") == "paragraph":
                    if "content" in node:
                        extract_recursive(node["content"])
                    text_parts.append("\n")
                # Recurse into content
                elif "content" in node:
                    extract_recursive(node["content"])

        extract_recursive(adf)
        return "".join(text_parts).strip()

    def _check_connection_sync(self) -> tuple[bool, str]:
        """Check if the Jira connection works (synchronous).

        Returns:
            Tuple of (success, message)
        """
        api_url = f"{self.url}/rest/api/3/myself"

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(api_url, auth=self._get_auth())
                response.raise_for_status()
                data = response.json()
                display_name = data.get("displayName", "Unknown")
                return True, f"Connected as {display_name}"
        except httpx.HTTPStatusError as e:
            return False, f"Auth failed: {e.response.status_code}"
        except httpx.RequestError as e:
            return False, f"Connection failed: {e}"
        except Exception as e:
            return False, f"Error: {e}"

    def check_config(self) -> HealthCheckResult:
        """Tier 1: Check configuration. No network calls.

        Returns:
            HealthCheckResult with status and details.
        """
        start = time.monotonic()

        # Check required config (these should exist if __init__ succeeded)
        missing = []
        if not self.url:
            missing.append("JIRA_URL")
        if not self.username:
            missing.append("JIRA_USERNAME")
        if not self.api_token:
            missing.append("JIRA_API_TOKEN")

        duration = int((time.monotonic() - start) * 1000)

        if missing:
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.FAILED,
                message=f"Missing: {', '.join(missing)}",
                duration_ms=duration,
            )

        return HealthCheckResult(
            name=self.name,
            status=HealthStatus.OK,
            message="Configuration valid",
            duration_ms=duration,
        )

    async def check_health(self) -> HealthCheckResult:
        """Check if this integration is working.

        Returns:
            HealthCheckResult with status and details.
        """
        start = time.monotonic()

        try:
            # Run sync check in executor to avoid blocking
            loop = asyncio.get_event_loop()
            success, message = await loop.run_in_executor(None, self._check_connection_sync)
            duration = int((time.monotonic() - start) * 1000)

            if success:
                return HealthCheckResult(
                    name=self.name,
                    status=HealthStatus.OK,
                    message=message,
                    duration_ms=duration,
                    tier=HealthCheckTier.CONNECTIVITY,
                )
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.FAILED,
                message=message,
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


# Module-level convenience functions
_client: JiraClient | None = None


def get_client() -> JiraClient:
    """Get or create the Jira client singleton."""
    global _client
    if _client is None:
        _client = JiraClient()
    return _client


def fetch_ticket(ticket_key: str) -> Ticket:
    """Fetch a Jira ticket by key.

    Convenience function that uses the default client.

    Args:
        ticket_key: The issue key (e.g., SPE-123)

    Returns:
        Ticket with issue details
    """
    return get_client().get_issue(ticket_key)


def check_jira_connection() -> tuple[bool, str]:
    """Check if Jira connection works.

    Returns:
        Tuple of (success, message)
    """
    try:
        client = JiraClient()
        return client._check_connection_sync()
    except ValueError as e:
        return False, str(e)


# Standalone test mode
if __name__ == "__main__":
    import asyncio
    import sys

    async def main() -> None:
        try:
            client = JiraClient()
            result = await client.check_health()
            print(f"{result.name}: {result.status.value} ({result.duration_ms}ms)")
            print(f"  {result.message}")

            if len(sys.argv) > 1:
                ticket_key = sys.argv[1].upper()
                print(f"\nFetching ticket {ticket_key}...")
                ticket = client.get_issue(ticket_key)
                print(f"  Key: {ticket.key}")
                print(f"  Summary: {ticket.summary}")
                print(f"  Status: {ticket.status}")
                print(f"  Type: {ticket.issue_type}")

            sys.exit(0 if result.status == HealthStatus.OK else 1)
        except ValueError as e:
            print(f"Configuration error: {e}")
            sys.exit(1)

    asyncio.run(main())
