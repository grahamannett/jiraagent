# Agent Configuration

This directory contains project-specific configuration for jira-agent.

## Files

- `deep-prompt.md` - Custom instructions for deep context generation (gitignored)
- `deep-prompt.md.example` - Template for creating your custom deep prompt

## Setup

1. Copy the example file:
   ```bash
   cp agent-config/deep-prompt.md.example agent-config/deep-prompt.md
   ```

2. Edit `deep-prompt.md` to match your project's structure and conventions.

## How It Works

When you run `jira-agent context generate --deep`, the generator:

1. Uses a **generic deep prompt** that works with any codebase
2. Looks for `agent-config/deep-prompt.md`
3. If found, appends your custom prompt as "PROJECT-SPECIFIC INSTRUCTIONS"
4. The combined prompt guides the AI to document your codebase thoroughly

## What to Include in Your Custom Prompt

Your custom prompt should document things specific to your project:

- **Project structure** - Where different types of code live
- **Naming conventions** - How files, functions, classes are named
- **Architecture patterns** - Lambda handlers, API routes, services, etc.
- **Data layer** - Entities, repositories, database structure
- **Common modifications** - Step-by-step guides for typical changes

See `deep-prompt.md.example` for a complete template.
