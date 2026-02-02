# Context Generation

This document explains how `jira-agent context generate` works and how to customize it.

## Overview

The context generator produces `AGENT.md` - a markdown document that gives AI agents understanding of your codebase. This context is injected into the agent's system prompt when processing Jira tickets.

**Two modes:**

- **Basic** (`context generate`): Fast static analysis (seconds)
- **Deep** (`context generate --deep`): AI-powered expansion (minutes)

## How It Works

```
CLI: jira-agent context generate [--deep]
         │
         ▼
    Static Analyzers
    ├── StructureAnalyzer  - Directory tree with file counts
    ├── TechStackAnalyzer  - Languages, frameworks, tools
    ├── LambdaAnalyzer     - AWS Lambda function detection
    ├── GraphQLAnalyzer    - Schema file discovery
    ├── RoutesAnalyzer     - Frontend route detection
    └── TestingAnalyzer    - Test framework detection
         │
         ▼
    Basic AGENT.md written
         │
         │ (if --deep)
         ▼
    AI Expansion (Claude Agent SDK)
    ├── Pass 1: Understand codebase structure
    ├── Pass 2: Deep API/entity/logic details
    └── Pass 3: Document patterns and guides
         │
         ▼
    Expanded AGENT.md
```

## Customizing Deep Mode

Deep mode uses a **generic prompt** that works with any codebase. For better results, add project-specific instructions:

```bash
# Copy the template
cp agent-config/deep-prompt.md.example agent-config/deep-prompt.md

# Edit for your project
vim agent-config/deep-prompt.md
```

When both exist, they're combined: generic base + your custom instructions.

See `agent-config/README.md` for details on what to include.

## Configuration

| File | Purpose |
|------|---------|
| `jira_agent/context/generator.py` | Generator implementation |
| `agent-config/deep-prompt.md.example` | Template for custom prompts |
| `agent-config/deep-prompt.md` | Your custom prompt (gitignored) |

## Storage

Context files are stored at `contexts/{repo_name}/AGENT.md` by default.

Override with `JIRA_AGENT_CONTEXTS_DIR` environment variable.

## Limitations

- **Monolithic deep run**: Long session with no checkpointing. If it fails, you restart from scratch.
- **Output is markdown**: No structured format for programmatic access.
- **No evaluation**: We don't measure context quality or relevance.

## Future Improvements

If we redesign the system, key principles:

1. **Task-shaped context**: Generate context relevant to the specific ticket, not a generic overview
2. **Hybrid approach**: Static extraction for structure, AI for semantics
3. **Resumability**: Checkpoint progress, allow incremental updates
4. **Evaluation**: Measure if context actually helps agents complete tasks
