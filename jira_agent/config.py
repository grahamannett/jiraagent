"""Application configuration using pydantic-settings."""

from pathlib import Path
import sys
from typing import ClassVar

from pydantic import AliasChoices, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Application configuration loaded from environment variables.

    Required:
        REPO_PATH: Path to the target repository
        WORKTREES_PATH: Path to git worktrees directory
        GITHUB_OWNER: GitHub organization or username
        GITHUB_REPO: GitHub repository name
        JIRA_URL: Jira instance URL (e.g., https://company.atlassian.net)

    Optional:
        GITHUB_PERSONAL_ACCESS_TOKEN or GITHUB_TOKEN: GitHub auth token

    Set these in mise.local.toml (see mise.local.toml.example) or export directly.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=None,  # Only read from environment variables, not files
    )

    repo: Path = Field(default=..., validation_alias="REPO_PATH")
    worktrees: Path = Field(default=..., validation_alias="WORKTREES_PATH")
    github_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "GITHUB_PERSONAL_ACCESS_TOKEN",
            "GITHUB_TOKEN",
        ),
    )
    github_owner: str = Field(default=..., validation_alias="GITHUB_OWNER")
    github_repo: str = Field(default=..., validation_alias="GITHUB_REPO")
    jira_url: str = Field(default=..., validation_alias="JIRA_URL")

    @classmethod
    def from_env(cls) -> "Config":
        try:
            return cls()
        except ValidationError as err:
            if missing := [e["loc"][0] for e in err.errors() if e["type"] == "missing"]:
                msg = f"Missing required env vars (set in mise.local.toml or export directly)\n {missing}"
                sys.exit(msg)
            sys.exit(f"Configuration error: {err}")
