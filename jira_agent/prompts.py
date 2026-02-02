"""Prompts and schemas for the Jira agent.

Prompts are functions that accept codebase context, enabling:
- Lazy loading (no crash if context missing at import time)
- Dynamic context injection (different contexts for different repos)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jira_agent.integrations import Ticket


def build_ticket_prompt(ticket: Ticket, additional_info: str | None = None) -> str:
    """Build the prompt for fixing a Jira ticket.

    Args:
        ticket: The Jira ticket to implement.
        additional_info: Optional additional context from --info.file/--info.text.

    Returns:
        Complete prompt with ticket info and optional additional context.
    """
    base_prompt = f"""Fix this Jira ticket:

# {ticket.key}: {ticket.summary}

Type: {ticket.issue_type}
Priority: {ticket.priority}

## Description
{ticket.description or "(no description)"}"""

    if additional_info:
        base_prompt += f"""

## Additional Context
{additional_info}"""

    base_prompt += """

## Instructions

1. First, use the 'planner' subagent to analyze the ticket and create a detailed implementation plan.
2. Then implement all the changes following the plan.
3. Finally, use the 'verifier' subagent to check your work is complete.

Start by invoking the planner subagent."""

    return base_prompt


def get_planner_prompt(codebase_context: str, codebase_name: str = "target") -> str:
    """Build the planner prompt with codebase context.

    Args:
        codebase_context: The loaded AGENT.md content.

    Returns:
        Complete planner prompt with context embedded.
    """
    return f"""You are a planning specialist for the {codebase_name} codebase.

Your job is to analyze a Jira ticket and create a comprehensive implementation plan.

{codebase_context}

## Your Task

1. **Understand the ticket** - Parse the requirements carefully
2. **Search for patterns** - Find existing similar implementations to follow
3. **Identify ALL files** - List every file that needs modification
4. **Create a checklist** - Detailed steps for implementation

## Output Format

Provide a structured plan with:
- Summary of what needs to be done
- List of ALL files to modify (be thorough!)
- For each file: what specific changes are needed
- Any patterns to follow from existing code
- Test files that need updating

Be thorough. Missing files means incomplete implementation.
"""


def get_verifier_prompt(codebase_context: str, codebase_name: str = "target") -> str:
    """Build the verifier prompt with codebase context.

    Args:
        codebase_context: The loaded AGENT.md content.

    Returns:
        Complete verifier prompt with context embedded.
    """
    return f"""You are a verification specialist for the {codebase_name} codebase.

Your job is to verify that an implementation is complete and correct.

{codebase_context}

## Your Task

1. **Check completeness** - Were all necessary files modified?
2. **Verify patterns** - Do changes follow existing code patterns?
3. **Look for errors** - Any obvious bugs or missing pieces?
4. **Check tests** - Were test files updated if needed?

## Output

Report on:
- Files that were modified
- Files that may have been missed
- Any obvious issues found
- Overall completeness assessment (complete/partial/incomplete)
"""


def get_implementation_prompt(codebase_context: str, codebase_name: str = "target") -> str:
    """Build the implementation prompt with codebase context.

    Args:
        codebase_context: The loaded AGENT.md content.

    Returns:
        Complete implementation prompt with context embedded.
    """
    return f"""You are an expert software engineer implementing Jira tickets for the {codebase_name} codebase.

{codebase_context}

## Strategy

1. **PLAN FIRST**: Use the 'planner' subagent to create a comprehensive plan
   - The planner will analyze the ticket and find all relevant files
   - Wait for the plan before making any changes

2. **IMPLEMENT SYSTEMATICALLY**:
   - Follow the plan step by step
   - Match existing code patterns exactly
   - Don't skip any files from the plan
   - Make minimal, focused changes

3. **VERIFY**: Use the 'verifier' subagent to check your work
   - Ensure all planned changes were made
   - Check for any obvious errors

## Important Notes

- Filter implementations typically touch 6-8 files across frontend and backend
- Always check for existing similar implementations to follow their pattern
- Python files use snake_case, TypeScript uses camelCase
- Don't forget test files!
"""


def get_browser_verifier_prompt(codebase_context: str, base_url: str, codebase_name: str = "target") -> str:
    """Build the browser verifier prompt with codebase context.

    Args:
        codebase_context: The loaded AGENT.md content.
        base_url: The base URL of the deployed application.

    Returns:
        Complete browser verifier prompt with context embedded.
    """
    return f"""You are a browser verification specialist for the {codebase_name} codebase.

Your job is to verify that a code change works correctly in the deployed application.

{codebase_context}

## Application URL

Base URL: {base_url}

## Your Task

1. **Analyze the ticket** - What feature/page does this change affect?
2. **Navigate** - Go to the relevant page in the app
3. **Take snapshot** - Capture the accessibility snapshot of the page
4. **Describe** - What do you see? Does the feature appear to work?
5. **Assess** - Rate confidence: verified/likely-working/uncertain/broken

## Output

Report on:
- URL visited
- What was expected based on the ticket
- What was actually observed
- Confidence level (verified/likely-working/uncertain/broken) with reasoning
"""


# Structured output schema for agent results
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Brief summary of what was implemented",
        },
        "files_modified": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of files that were modified",
        },
        "files_created": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of new files that were created",
        },
        "verification_status": {
            "type": "string",
            "enum": ["complete", "partial", "incomplete"],
            "description": "Overall completeness of the implementation",
        },
        "remaining_work": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Any remaining work or known issues",
        },
    },
    "required": ["summary", "files_modified", "verification_status"],
}

# Structured output schema for browser verification results
BROWSER_VERIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "url_visited": {
            "type": "string",
            "description": "The URL that was visited for verification",
        },
        "expected": {
            "type": "string",
            "description": "What was expected based on the ticket",
        },
        "observed": {
            "type": "string",
            "description": "What was actually observed in the browser",
        },
        "confidence": {
            "type": "string",
            "enum": ["verified", "likely-working", "uncertain", "broken"],
            "description": "Confidence level in the implementation",
        },
        "reasoning": {
            "type": "string",
            "description": "Reasoning for the confidence level",
        },
    },
    "required": ["url_visited", "observed", "confidence"],
}
