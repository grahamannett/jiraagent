# Jira Agent

CLI tool that fetches Jira tickets and uses Claude to implement code changes.

## Overview

Jira Agent automates software development tasks by:

1. **Fetching Jira tickets** - Retrieves ticket details via Atlassian MCP
2. **Creating isolated workspaces** - Uses Git worktrees or branches for each ticket
3. **AI-powered implementation** - Uses Claude with specialized subagents:
   - **Planner** - Analyzes tickets and creates implementation plans
   - **Implementer** - Makes code changes following project patterns
   - **Verifier** - Checks implementation completeness
4. **Browser verification** (optional) - Uses Playwright to verify changes work in the deployed app
5. **Generating context** - Creates `AGENT.md` to give the AI deep understanding of your codebase

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        jira-agent CLI                           │
├─────────────────────────────────────────────────────────────────┤
│  Commands:                                                      │
│  • run <KEY>     - Process a Jira ticket                        │
│  • cleanup <KEY> - Remove worktree after completion             │
│  • ticket <KEY>  - View ticket details                          │
│  • context       - Manage AGENT.md codebase documentation       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Claude Agent SDK                            │
├─────────────────────────────────────────────────────────────────┤
│  Main Agent (claude_code preset)                                │
│  ├── Tools: Read, Edit, Write, Glob, Grep, Bash, Task           │
│  └── Subagents:                                                 │
│      ├── planner  - Analyzes tickets, creates plans             │
│      └── verifier - Verifies implementation completeness        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Target Codebase                            │
│  (isolated in Git worktree or branch per ticket)                │
└─────────────────────────────────────────────────────────────────┘
```

### Subagent Architecture

| Subagent   | Purpose                            | Tools                  | Model  |
| ---------- | ---------------------------------- | ---------------------- | ------ |
| `planner`  | Analyze tickets, create plans      | Read, Glob, Grep       | Sonnet |
| `verifier` | Verify implementation completeness | Read, Glob, Grep, Bash | Sonnet |

## Setup

```bash
git clone <repo-url>
cd jiraagent
uv sync
```

**Prerequisites:**

- Python 3.11+
- [mise](https://mise.jdx.dev/) for environment management (recommended)
- Jira API token from [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens)

**Environment setup:**

1. Copy the example configuration:

   ```bash
   cp mise.local.toml.example mise.local.toml
   ```

2. Edit `mise.local.toml` with your values:

   ```bash
   # Set the base directory for your repos
   export SCDIR=/path/to/your/repos  # e.g., ~/code/mycompany
   ```

3. Required environment variables (set in `mise.local.toml` or export directly):
   - `REPO_PATH` - Path to the target repository
   - `WORKTREES_PATH` - Path to git worktrees directory
   - `GITHUB_OWNER` - GitHub organization or username
   - `GITHUB_REPO` - GitHub repository name
   - `JIRA_URL` - Jira instance URL (e.g., `https://company.atlassian.net`)
   - `JIRA_USERNAME` - Your Jira/Atlassian email
   - `JIRA_API_TOKEN` - Your Jira API token

**Verify setup:**

```bash
uv run jira-agent health        # Quick config validation
uv run jira-agent health --full # Full connectivity check
```

## Development and Testing

Install dev dependencies from `pyproject.toml` (the `dev` extra), then run pytest:

```bash
uv sync --extra dev
uv run pytest
```

If you want all optional dependency groups, use `uv sync --all-extras`.

## Migration Note

**Breaking change in v1.0**: `GITHUB_OWNER`, `GITHUB_REPO`, and `JIRA_URL` are now required environment variables (previously had defaults). Create `mise.local.toml` from the example template to configure these.

## Usage

```bash
# Process a ticket (creates isolated worktree)
uv run jira-agent run SPE-123

# Process in main repo (better for deployment testing)
uv run jira-agent run SPE-123 --branch                    # auto-creates branch
uv run jira-agent run SPE-123 --branch my-feature-branch  # use specific branch

# Browser verification (requires --branch mode)
uv run jira-agent run SPE-123 --branch --verify           # verify after deploy
uv run jira-agent run SPE-123 --branch --verify --verify-url http://localhost:8080

# Other commands
uv run jira-agent run SPE-123 --dry-run   # preview ticket without processing
uv run jira-agent ticket SPE-123          # view ticket details
uv run jira-agent cleanup SPE-123         # remove worktree

# For evaluation: start from a specific commit (useful for comparing against existing PRs)
uv run jira-agent run SPE-123 --base-commit abc123f

# Health checks (useful for debugging)
uv run jira-agent health                  # fast config validation (default)
uv run jira-agent health --full           # also check connectivity (slower)
uv run jira-agent health --full --playwright  # include browser MCP

# Provide additional context for the agent
uv run jira-agent run SPE-123 --info-text="Focus on backend changes"
uv run jira-agent run SPE-123 --info-file=./notes/testing.md
uv run jira-agent run SPE-123 --info-file=./notes/patterns.md --info-text="Add integration tests"

# Audit logging (for debugging agent behavior)
uv run jira-agent run SPE-123 --audit-log=./audit.log
uv run jira-agent run SPE-123 --audit-stderr  # also log to stderr
```

## Security

The agent includes built-in security hooks that block dangerous operations:

**Blocked file paths:**

- `.git/` directory
- `.env` files
- `node_modules/`
- `.ssh/`, `.aws/`, `.gnupg/` directories

**Blocked commands:**

- `rm -rf /`, `sudo`, `su`, `doas`
- `chmod 777`, `chown -R`
- `git push --force`, `git reset --hard`
- Commands piping to bash/sh (`curl ... | bash`)

## Context Generation

Generate `AGENT.md` before first run (gives Claude codebase understanding):

```bash
uv run jira-agent context generate         # fast, static analysis
uv run jira-agent context generate --deep  # slow, AI-powered (recommended)
```

**Storage:** Context files are stored at `contexts/{repo_name}/AGENT.md` by default. Override with `JIRA_AGENT_CONTEXTS_DIR` env var.

**Commands:**

```bash
# Generate context
uv run jira-agent context generate              # basic static analysis
uv run jira-agent context generate --deep       # AI-powered deep analysis
uv run jira-agent context generate --force      # overwrite existing
uv run jira-agent context generate --output /custom/path/AGENT.md

# View context
uv run jira-agent context show                  # display current context
uv run jira-agent context path                  # show default context path
```

**Using context with `run`:**

```bash
uv run jira-agent run SPE-123                           # uses default context
uv run jira-agent run SPE-123 --context /path/AGENT.md  # use specific context
```

**Basic Context** (`context generate`):

- Static analysis using Python analyzers
- Fast (seconds)
- Captures: structure, tech stack, lambda functions, GraphQL schema, testing setup

**Deep Context** (`context generate --deep`):

- AI-powered exploration using Claude Agent SDK
- Three-pass approach:
  1. **Pass 1**: Understand the codebase structure
  2. **Pass 2**: Deep API, entity, and business logic details
  3. **Pass 3**: Document patterns and guides
- Slow (several minutes)
- Produces comprehensive documentation

**Customizing Deep Context:**

For project-specific deep analysis, create a custom prompt:

```bash
cp agent-config/deep-prompt.md.example agent-config/deep-prompt.md
# Edit agent-config/deep-prompt.md for your project
```

See `agent-config/README.md` for details.

## How It Works

```
uv run jira-agent run SPE-123
         │
         ▼
┌────────────────────┐
│  Fetch Jira Ticket │
│  (via MCP)         │
└────────────────────┘
         │
         ▼
┌────────────────────┐
│  Create Workspace  │
│  (worktree/branch) │
└────────────────────┘
         │
         ▼
┌────────────────────┐
│  Launch Agent      │
│                    │
│  1. Planner        │◄─── Analyzes ticket, finds patterns,
│     subagent       |   creates implementation plan
│                    │
│  2. Main agent     │◄─── Implements changes following
│     implements     |    the plan
│                    │
│  3. Verifier       │◄─── Checks completeness,
│     subagent           reports any gaps
└────────────────────┘
         │
         ▼
┌────────────────────┐
│  Report Results    │
│  - Files modified  │
│  - Verification    │
│  - Remaining work  │
└────────────────────┘
```

## Browser Verification

The `--verify` flag enables optional browser-based verification using Playwright MCP. After the agent implements changes, it can visually verify the fix works in the deployed application.

**Requirements:**

- Must use `--branch` mode (worktrees don't support deployment)
- Playwright MCP server must be configured in Claude Code

**How it works:**

1. Agent implements the ticket changes
2. Agent pauses and prompts you to deploy:
   ```
   READY FOR BROWSER VERIFICATION
   Please deploy your changes now.
   Press Enter when the app is running (Ctrl+C to skip)...
   ```
3. You deploy and press Enter
4. Agent uses Playwright to:
   - Navigate to the relevant page (extracted from ticket)
   - Take an accessibility snapshot
   - Assess whether the change appears to work
   - Report confidence: `verified`, `likely-working`, `uncertain`, or `broken`

**Options:**

| Flag           | Default                 | Description                                      |
| -------------- | ----------------------- | ------------------------------------------------ |
| `--verify`     | disabled                | Enable browser verification after implementation |
| `--verify-url` | `http://localhost:3000` | Base URL for the deployed application            |

**Example output:**

```
🌐 Browser Verification:
   URL: http://localhost:3000/transactions
   Observed: Filter dropdown now shows merchant category option
   Confidence: verified
   Reasoning: The new filter is visible and functional
```

## Output Example

```
============================================================
DONE: Implemented transaction filter for merchant category

Files Modified (6):
   - src/components/filters/MerchantCategoryFilter.tsx
   - src/hooks/useTransactionFilters.ts
   - backend/functions/transaction/domains/search.py
   - backend/api/schema/transaction.graphql
   - tests/components/MerchantCategoryFilter.test.tsx
   - tests/domains/test_search.py

Verification: complete

Worktree: /path/to/worktrees/spe-123
============================================================
```

- **Files Modified**: All files the agent touched
- **Verification**: Subagent's assessment (`complete`, `partial`, `incomplete`)
- **Worktree/Branch**: Location to review changes

## Troubleshooting

### Jira Connection Issues

If you encounter errors fetching tickets, check your Jira API credentials.

**Check configuration (fast):**

```bash
uv run jira-agent health
```

**Expected output:**

```
Checking configuration...

  [OK] Jira HTTP (0ms)
       Configuration valid
  [OK] Jira MCP (0ms)
       Configuration valid
  [OK] Browser MCP (Chrome DevTools) (0ms)
       Configuration valid

All checks passed.
```

**Check connectivity (slower):**

```bash
uv run jira-agent health --full
```

This also tests actual API connectivity after config validation.

**Common errors:**

| Error                                         | Solution                                                                                              |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `JIRA_URL environment variable not set`       | Set `JIRA_URL` or use mise with the default                                                           |
| `JIRA_USERNAME environment variable not set`  | Set `JIRA_USERNAME` to your Atlassian email                                                           |
| `JIRA_API_TOKEN environment variable not set` | Create a token at [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |
| `Auth failed: 401`                            | Check your API token is valid and not expired                                                         |
| `Ticket XXX not found`                        | Verify the ticket key exists in Jira                                                                  |

See [PLAN.md](PLAN.md) for development roadmap and active work.
