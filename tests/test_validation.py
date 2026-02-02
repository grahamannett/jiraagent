"""Tests for input validation."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from jira_agent.validation import (
    ValidationError,
    validate_env_vars,
    validate_git_state,
    validate_repo_path,
    validate_ticket_key,
)


class TestValidateTicketKey:
    """Tests for ticket key validation."""

    @pytest.mark.parametrize(
        "key",
        [
            "SPE-123",
            "PROJECT-1",
            "ABC123-456",
            "A-1",
            "AB-999999",
            "TEST-0",
        ],
        ids=["standard", "long-project", "alphanumeric-project", "minimal", "large-number", "zero"],
    )
    def test_valid_ticket_keys(self, key):
        """Valid ticket keys should pass validation."""
        # Should not raise
        validate_ticket_key(key)

    @pytest.mark.parametrize(
        ("key", "reason"),
        [
            ("spe-123", "lowercase project"),
            ("SPE123", "missing hyphen"),
            ("123-SPE", "number prefix"),
            ("-123", "missing project"),
            ("SPE-", "missing number"),
            ("SPE-abc", "non-numeric suffix"),
            ("", "empty string"),
            ("SPE_123", "underscore instead of hyphen"),
            ("spe-ABC", "lowercase with letters"),
        ],
        ids=[
            "lowercase",
            "no-hyphen",
            "number-prefix",
            "no-project",
            "no-number",
            "alpha-suffix",
            "empty",
            "underscore",
            "lowercase-letters",
        ],
    )
    def test_invalid_ticket_keys(self, key, reason):
        """Invalid ticket keys should raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_ticket_key(key)

        assert "Invalid ticket key format" in str(exc_info.value) or "cannot be empty" in str(
            exc_info.value
        )


class TestValidateEnvVars:
    """Tests for environment variable validation."""

    def test_all_vars_set(self):
        """Validation passes when all required vars are set."""
        env = {
            "JIRA_URL": "https://example.atlassian.net",
            "JIRA_USERNAME": "user@example.com",
            "JIRA_API_TOKEN": "secret-token",
        }
        with patch.dict(os.environ, env, clear=True):
            # Should not raise
            validate_env_vars()

    def test_missing_single_var(self):
        """Validation fails when one var is missing."""
        env = {
            "JIRA_URL": "https://example.atlassian.net",
            "JIRA_USERNAME": "user@example.com",
            # JIRA_API_TOKEN missing
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                validate_env_vars()

            assert "JIRA_API_TOKEN" in str(exc_info.value)

    def test_missing_multiple_vars(self):
        """Validation fails and lists all missing vars."""
        env = {
            "JIRA_URL": "https://example.atlassian.net",
            # Others missing
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                validate_env_vars()

            error_msg = str(exc_info.value)
            assert "JIRA_USERNAME" in error_msg
            assert "JIRA_API_TOKEN" in error_msg

    def test_empty_var_treated_as_missing(self):
        """Empty string values are treated as missing."""
        env = {
            "JIRA_URL": "https://example.atlassian.net",
            "JIRA_USERNAME": "",  # Empty
            "JIRA_API_TOKEN": "   ",  # Whitespace only
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                validate_env_vars()

            error_msg = str(exc_info.value)
            assert "JIRA_USERNAME" in error_msg
            assert "JIRA_API_TOKEN" in error_msg


class TestValidateGitState:
    """Tests for git state validation."""

    def test_clean_repo_passes(self, tmp_path):
        """Clean repository passes validation."""
        # Create a git repo with initial commit
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Create a file and commit it
        (tmp_path / "file.txt").write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Should not raise
        validate_git_state(tmp_path)

    def test_dirty_repo_fails(self, tmp_path):
        """Repository with uncommitted changes fails validation."""
        # Create a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Create and commit a file
        (tmp_path / "file.txt").write_text("content")
        subprocess.run(["git", "add", "file.txt"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Modify the file without committing
        (tmp_path / "file.txt").write_text("modified content")

        with pytest.raises(ValidationError) as exc_info:
            validate_git_state(tmp_path)

        assert "Uncommitted changes" in str(exc_info.value)
        assert "file.txt" in str(exc_info.value)

    def test_nonexistent_path_fails(self, tmp_path):
        """Nonexistent path fails validation."""
        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(ValidationError) as exc_info:
            validate_git_state(nonexistent)

        assert "does not exist" in str(exc_info.value)

    def test_non_git_repo_fails(self, tmp_path):
        """Non-git directory fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            validate_git_state(tmp_path)

        assert "Not a git repository" in str(exc_info.value)


class TestValidateRepoPath:
    """Tests for repository path validation."""

    def test_valid_git_repo(self, tmp_path):
        """Valid git repository passes validation."""
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

        # Should not raise
        validate_repo_path(tmp_path)

    def test_nonexistent_path_fails(self, tmp_path):
        """Nonexistent path fails validation."""
        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(ValidationError) as exc_info:
            validate_repo_path(nonexistent)

        assert "does not exist" in str(exc_info.value)

    def test_file_instead_of_dir_fails(self, tmp_path):
        """File path instead of directory fails validation."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        with pytest.raises(ValidationError) as exc_info:
            validate_repo_path(file_path)

        assert "not a directory" in str(exc_info.value)

    def test_non_git_dir_fails(self, tmp_path):
        """Non-git directory fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            validate_repo_path(tmp_path)

        assert "Not a git repository" in str(exc_info.value)
