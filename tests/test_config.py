"""Tests for Config using pydantic-settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from jira_agent.config import Config


def _set_required_env(monkeypatch):
    """Set all required env vars for a valid config."""
    monkeypatch.setenv("REPO_PATH", "/tmp/repo")
    monkeypatch.setenv("WORKTREES_PATH", "/tmp/worktrees")
    monkeypatch.setenv("GITHUB_OWNER", "test-org")
    monkeypatch.setenv("GITHUB_REPO", "test-repo")
    monkeypatch.setenv("JIRA_URL", "https://test.atlassian.net")


class TestConfig:
    """Tests for the pydantic-settings Config class."""

    def test_loads_required_fields(self, monkeypatch):
        """Required fields are loaded from environment."""
        _set_required_env(monkeypatch)

        cfg = Config()

        assert cfg.repo == Path("/tmp/repo")
        assert cfg.worktrees == Path("/tmp/worktrees")
        assert cfg.github_owner == "test-org"
        assert cfg.github_repo == "test-repo"
        assert cfg.jira_url == "https://test.atlassian.net"

    def test_missing_required_raises(self, monkeypatch):
        """Missing required fields raise ValidationError."""
        monkeypatch.delenv("REPO_PATH", raising=False)
        monkeypatch.delenv("WORKTREES_PATH", raising=False)
        monkeypatch.delenv("GITHUB_OWNER", raising=False)
        monkeypatch.delenv("GITHUB_REPO", raising=False)
        monkeypatch.delenv("JIRA_URL", raising=False)

        with pytest.raises(ValidationError):
            Config()

    def test_missing_repo_path_raises(self, monkeypatch):
        """Missing REPO_PATH alone raises ValidationError."""
        _set_required_env(monkeypatch)
        monkeypatch.delenv("REPO_PATH", raising=False)

        with pytest.raises(ValidationError):
            Config()

    def test_missing_worktrees_path_raises(self, monkeypatch):
        """Missing WORKTREES_PATH alone raises ValidationError."""
        _set_required_env(monkeypatch)
        monkeypatch.delenv("WORKTREES_PATH", raising=False)

        with pytest.raises(ValidationError):
            Config()

    def test_missing_github_owner_raises(self, monkeypatch):
        """Missing GITHUB_OWNER raises ValidationError."""
        _set_required_env(monkeypatch)
        monkeypatch.delenv("GITHUB_OWNER", raising=False)

        with pytest.raises(ValidationError):
            Config()

    def test_missing_github_repo_raises(self, monkeypatch):
        """Missing GITHUB_REPO raises ValidationError."""
        _set_required_env(monkeypatch)
        monkeypatch.delenv("GITHUB_REPO", raising=False)

        with pytest.raises(ValidationError):
            Config()

    def test_missing_jira_url_raises(self, monkeypatch):
        """Missing JIRA_URL raises ValidationError."""
        _set_required_env(monkeypatch)
        monkeypatch.delenv("JIRA_URL", raising=False)

        with pytest.raises(ValidationError):
            Config()

    def test_github_token_defaults_empty(self, monkeypatch):
        """GITHUB_TOKEN defaults to empty string when not set."""
        _set_required_env(monkeypatch)
        monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        cfg = Config()

        assert cfg.github_token == ""

    def test_github_token_primary(self, monkeypatch):
        """GITHUB_PERSONAL_ACCESS_TOKEN is preferred over GITHUB_TOKEN."""
        _set_required_env(monkeypatch)
        monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "primary-token")
        monkeypatch.setenv("GITHUB_TOKEN", "fallback-token")

        cfg = Config()

        assert cfg.github_token == "primary-token"

    def test_github_token_fallback(self, monkeypatch):
        """GITHUB_TOKEN is used as fallback when primary not set."""
        _set_required_env(monkeypatch)
        monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "fallback-token")

        cfg = Config()

        assert cfg.github_token == "fallback-token"

    def test_path_conversion(self, monkeypatch):
        """String env vars are converted to Path objects."""
        _set_required_env(monkeypatch)

        cfg = Config()

        assert isinstance(cfg.repo, Path)
        assert isinstance(cfg.worktrees, Path)
