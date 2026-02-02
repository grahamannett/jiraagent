"""Codebase context generator with optional AI-powered deep expansion.

This module provides both static analysis and AI-powered deep context generation.
Use `deep=True` to expand basic context with comprehensive handler, entity, and
pattern documentation.

Usage:
    generator = ContextGenerator()

    # Basic (fast, static analysis)
    content = generator.generate(repo_path, output_file)

    # Deep (slow, AI-powered expansion)
    content = generator.generate(repo_path, output_file, deep=True)
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, override

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)

from jira_agent.log import log, print  # noqa: A004


# --- Analysis Result ---


@dataclass
class AnalysisResult:
    """Structured output from an analyzer."""

    section_name: str
    content: str
    order: int = 0  # Lower numbers appear first
    metadata: dict[str, Any] = field(default_factory=dict)


# --- Static Analyzers ---


class CodebaseAnalyzer(ABC):
    """Abstract base for codebase analysis strategies.

    Subclass this to add new analysis capabilities. Each analyzer
    produces a markdown section for the final context document.
    """

    @abstractmethod
    def analyze(self, repo_path: Path) -> AnalysisResult | None:
        """Analyze the codebase and return a result section.

        Returns None if this analyzer doesn't apply to the given repo.
        """
        ...


class StructureAnalyzer(CodebaseAnalyzer):
    """Analyzes directory structure and file counts."""

    SKIP_DIRS: set[str] = {
        "node_modules",
        ".git",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".next",
        "coverage",
        ".nyc_output",
        "#current-cloud-backend",
        ".amplify",
        ".vscode",
        ".idea",
    }

    @override
    def analyze(self, repo_path: Path) -> AnalysisResult:
        structure = self._scan_structure(repo_path, depth=2)
        content = self._format_structure(structure)
        return AnalysisResult(
            section_name="Project Structure",
            content=content,
            order=10,
        )

    def _scan_structure(self, path: Path, depth: int, prefix: str = "") -> list[str]:
        if depth <= 0 or not path.is_dir():
            return []

        lines = []
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return []

        for entry in entries:
            if entry.name.startswith(".") and entry.name not in {".github"}:
                continue
            if entry.name in self.SKIP_DIRS:
                continue

            if entry.is_dir():
                file_count = self._count_files(entry)
                lines.append(f"{prefix}- `{entry.name}/` ({file_count} files)")
                lines.extend(self._scan_structure(entry, depth - 1, prefix + "  "))
            elif depth == 2:
                lines.append(f"{prefix}- `{entry.name}`")

        return lines

    def _count_files(self, path: Path) -> int:
        count = 0
        try:
            for entry in path.rglob("*"):
                if entry.is_file() and not any(skip in entry.parts for skip in self.SKIP_DIRS):
                    count += 1
        except PermissionError:
            pass
        return count

    def _format_structure(self, lines: list[str]) -> str:
        return "\n".join(lines) if lines else "(empty)"


class TechStackAnalyzer(CodebaseAnalyzer):
    """Detects technology stack from configuration files."""

    @override
    def analyze(self, repo_path: Path) -> AnalysisResult:
        techs = []

        pkg_json = repo_path / "package.json"
        if pkg_json.exists():
            techs.extend(self._analyze_package_json(pkg_json))

        for pyfile in ["Pipfile", "pyproject.toml", "requirements.txt"]:
            if (repo_path / pyfile).exists():
                techs.append(f"Python (via {pyfile})")
                break

        if (repo_path / "amplify").is_dir():
            techs.append("AWS Amplify")

        if (repo_path / "amplify/backend/api").is_dir():
            techs.append("GraphQL API (AppSync)")

        if (repo_path / "tailwind.config.js").exists():
            techs.append("Tailwind CSS")

        content = self._format_techs(techs)
        return AnalysisResult(
            section_name="Technology Stack",
            content=content,
            order=20,
            metadata={"technologies": techs},
        )

    def _analyze_package_json(self, pkg_path: Path) -> list[str]:
        techs = []
        try:
            data = json.loads(pkg_path.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

            if "react" in deps:
                techs.append("React")
            if "typescript" in deps or (pkg_path.parent / "tsconfig.json").exists():
                techs.append("TypeScript")
            if "@reduxjs/toolkit" in deps:
                techs.append("Redux Toolkit")
            if "@mui/material" in deps:
                techs.append("Material-UI (MUI)")
            if "jest" in deps:
                techs.append("Jest (testing)")
            if "@tanstack/react-table" in deps:
                techs.append("TanStack Table")

        except (json.JSONDecodeError, OSError):
            pass

        return techs

    def _format_techs(self, techs: list[str]) -> str:
        if not techs:
            return "(no technologies detected)"
        return "\n".join(f"- {tech}" for tech in techs)


class LambdaAnalyzer(CodebaseAnalyzer):
    """Analyzes AWS Lambda function structure."""

    @override
    def analyze(self, repo_path: Path) -> AnalysisResult | None:
        functions_dir = repo_path / "amplify/backend/function"
        if not functions_dir.is_dir():
            return None

        v2_functions = []
        legacy_functions = []

        for fn_dir in sorted(functions_dir.iterdir()):
            if not fn_dir.is_dir():
                continue
            name = fn_dir.name
            if name.startswith("v2"):
                v2_functions.append(name)
            else:
                legacy_functions.append(name)

        content_lines = []
        if v2_functions:
            content_lines.append("### v2 Functions (Domain-Driven)")
            for fn in v2_functions:
                content_lines.append(f"- `{fn}`")

        if legacy_functions:
            content_lines.append("\n### Legacy Functions")
            for fn in legacy_functions:
                content_lines.append(f"- `{fn}`")

        return AnalysisResult(
            section_name="Lambda Functions",
            content="\n".join(content_lines),
            order=30,
            metadata={"v2": v2_functions, "legacy": legacy_functions},
        )


class GraphQLAnalyzer(CodebaseAnalyzer):
    """Analyzes GraphQL schema structure."""

    @override
    def analyze(self, repo_path: Path) -> AnalysisResult | None:
        schema_dir = repo_path / "amplify/backend/api"
        if not schema_dir.is_dir():
            return None

        schema_files = list(schema_dir.rglob("*.graphql"))
        if not schema_files:
            return None

        content_lines = ["Schema files:"]
        for sf in sorted(schema_files):
            rel_path = sf.relative_to(repo_path)
            content_lines.append(f"- `{rel_path}`")

        return AnalysisResult(
            section_name="GraphQL Schema",
            content="\n".join(content_lines),
            order=40,
        )


class RoutesAnalyzer(CodebaseAnalyzer):
    """Analyzes frontend routing for browser verification support."""

    @override
    def analyze(self, repo_path: Path) -> AnalysisResult | None:
        # Look for React Router configuration
        routes: list[str] = []

        # Check for common route configuration patterns
        src_dir = repo_path / "src"
        if not src_dir.is_dir():
            return None

        # Look for route files
        route_patterns = ["routes", "router", "routing", "Routes", "Router"]
        for pattern in route_patterns:
            for ext in [".tsx", ".ts", ".jsx", ".js"]:
                route_file = src_dir / f"app/{pattern}{ext}"
                if route_file.exists():
                    routes.append(f"- Route config: `{route_file.relative_to(repo_path)}`")
                    break

        # Look for pages directory (Next.js style or custom)
        pages_dir = src_dir / "pages"
        if pages_dir.is_dir():
            routes.append(f"- Pages directory: `{pages_dir.relative_to(repo_path)}`")

        # Look for app directory patterns
        app_dir = src_dir / "app"
        if app_dir.is_dir():
            # Scan for feature directories that likely map to routes
            for subdir in sorted(app_dir.iterdir()):
                if subdir.is_dir() and not subdir.name.startswith("_"):
                    routes.append(f"- Feature: `/{subdir.name}`")

        if not routes:
            return None

        content_lines = [
            "Routes detected (for browser verification):",
            "",
            *routes,
            "",
            "_Note: Run `jira-agent context generate --deep` to get complete route mapping._",
        ]

        return AnalysisResult(
            section_name="App Routes (Browser Verification)",
            content="\n".join(content_lines),
            order=55,  # After testing
        )


class TestingAnalyzer(CodebaseAnalyzer):
    """Analyzes testing structure and conventions."""

    @override
    def analyze(self, repo_path: Path) -> AnalysisResult:
        findings = []

        if (repo_path / "jest.config.js").exists():
            findings.append("- **Frontend**: Jest (see `jest.config.js`)")

        if (repo_path / "pytest.ini").exists() or (repo_path / ".pytest_cache").is_dir():
            findings.append("- **Backend (Python)**: pytest (see `pytest.ini`)")

        lambda_tests = list((repo_path / "amplify/backend/function").rglob("tests"))
        if lambda_tests:
            findings.append(f"- **Lambda tests**: Found in {len(lambda_tests)} function(s)")

        content = "\n".join(findings) if findings else "(no testing setup detected)"
        return AnalysisResult(
            section_name="Testing",
            content=content,
            order=50,
        )


# --- Deep Expansion Prompt ---

# Placeholder replaced with actual output path at runtime
_OUTPUT_FILE_PLACEHOLDER = "{{OUTPUT_FILE}}"
_N_PASSES_PLACEHOLDER = "THREE"

# Path to custom project-specific deep prompt
_CUSTOM_PROMPT_PATH = Path("agent-config/deep-prompt.md")

_GENERIC_DEEP_PROMPT = f"""You are a technical documentation expert. A basic codebase overview has already been written to `{_OUTPUT_FILE_PLACEHOLDER}`.

Your task is to READ this existing file and EXPAND it with deep, comprehensive details in {_N_PASSES_PLACEHOLDER} PASSES.

## CRITICAL INSTRUCTIONS

1. **READ FIRST**: Start by reading `{_OUTPUT_FILE_PLACEHOLDER}` to see what's already documented
2. **USE EDIT TOOL**: Use the Edit tool to ADD content to existing sections - do NOT rewrite from scratch
3. **ADD NEW SECTIONS**: Create new sections for deep details not in the basic overview
4. **BE EXHAUSTIVE**: Read actual file contents and document specific details (function signatures, parameters, return types, docstrings)
5. **DO NOT DELETE**: Never remove existing content - only expand it

---

# PASS 1: UNDERSTAND THE CODEBASE

## Step 1.1: Read Existing Documentation
Read `{_OUTPUT_FILE_PLACEHOLDER}` to understand what's already documented.

## Step 1.2: Identify Project Type
Determine what kind of project this is by examining:
- Package files: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, etc.
- Framework indicators: React, Django, FastAPI, Express, Rails, etc.
- Infrastructure: AWS, GCP, Docker, Kubernetes, serverless, etc.

## Step 1.3: Expand Project Structure
The basic overview has directory structure. ADD:
- File counts per major directory
- Key configuration files and their purposes
- Entry points (main files, index files, etc.)

## Step 1.4: Expand Technology Stack
The basic overview lists technologies. ADD:
- Version numbers from package/config files
- Key dependencies and what they're used for
- Development vs production dependencies

---

# PASS 2: DEEP DETAILS

## Step 2.1: API/Endpoint Documentation
Find and document all API endpoints, routes, or handlers:
- For REST APIs: HTTP method, path, parameters, response format
- For GraphQL: queries, mutations, subscriptions
- For CLI tools: commands, arguments, options
- For libraries: public functions and classes

## Step 2.2: Data Models/Entities
Document the core data structures:
- Database models/entities with all fields and types
- TypeScript/Python types and interfaces
- Relationships between entities
- Indexes, constraints, validations

## Step 2.3: Business Logic
For each major module/domain:
- Read the main source files
- Document key functions with signatures and docstrings
- Note dependencies and side effects
- Document error handling patterns

## Step 2.4: Configuration and Environment
Document all configuration:
- Environment variables used (search for `process.env`, `os.environ`, `os.getenv`)
- Configuration files and their schemas
- Feature flags or toggles
- Secrets management

## Step 2.5: Testing Patterns
Document the testing approach:
- Test frameworks used
- Test directory structure
- Fixture and mock patterns
- How to run tests

---

# PASS 3: PATTERNS AND GUIDES

## Step 3.1: Code Patterns
Document recurring patterns in the codebase:
- How new features are typically added
- Common abstractions and base classes
- Error handling conventions
- Logging conventions

## Step 3.2: Common Modification Guides
Create step-by-step guides for common changes:
- Adding a new API endpoint/route
- Adding a new data model/entity
- Adding a new command/handler
- Modifying existing functionality

## Step 3.3: Deployment and Operations
Document deployment and operational details:
- Build commands and scripts
- Deployment process
- Monitoring and logging
- Common debugging approaches

## Step 3.4: Frontend Routes (if applicable)
If this is a web application with a frontend:
- Document all routes/pages
- Map routes to components
- Note authentication requirements
- Document navigation structure

---

# VALIDATION

At the END, add a coverage report section that lists:
- Sections documented
- Key files read
- Any areas that need more documentation

---

BEGIN NOW. Start with Pass 1, Step 1.1 - READ the existing file.
Complete ALL {_N_PASSES_PLACEHOLDER} PASSES before finishing."""


def _load_custom_deep_prompt() -> str | None:
    """Load custom project-specific deep prompt if it exists.

    Looks for agent-config/deep-prompt.md in the current working directory.

    Returns:
        The custom prompt content, or None if not found.
    """
    if _CUSTOM_PROMPT_PATH.exists():
        return _CUSTOM_PROMPT_PATH.read_text()
    return None


# --- Metadata Header ---


def _build_metadata_header(repo_path: Path, deep: bool, line_count: int) -> str:
    """Build metadata header for generated context file.

    The header provides information about when and how the context was generated,
    allowing validation and staleness detection.
    """
    return f"""<!-- AGENT.md Context File
     Generated: {datetime.now().isoformat()}
     Mode: {"deep" if deep else "basic"}
     Repository: {repo_path}
     Lines: {line_count}
-->

"""


# --- Context Generator ---


class ContextGenerator:
    """Generates codebase context documentation.

    Supports two modes:
    - Basic (default): Fast static analysis using pluggable analyzers
    - Deep: AI-powered expansion with comprehensive documentation
    """

    DEFAULT_ANALYZERS: list[type[CodebaseAnalyzer]] = [
        StructureAnalyzer,
        TechStackAnalyzer,
        LambdaAnalyzer,
        GraphQLAnalyzer,
        RoutesAnalyzer,
        TestingAnalyzer,
    ]

    analyzers: list[CodebaseAnalyzer]

    def __init__(self, analyzers: list[CodebaseAnalyzer] | None = None):
        """Initialize with custom or default analyzers."""
        if analyzers is None:
            analyzers = [cls() for cls in self.DEFAULT_ANALYZERS]
        self.analyzers = analyzers

    def generate(self, repo_path: Path, output_file: Path, deep: bool = False) -> str:
        """Generate context documentation for a repository.

        Args:
            repo_path: Path to the repository to analyze.
            output_file: Path where documentation will be written.
            deep: If True, use AI to expand with comprehensive details.

        Returns:
            The generated markdown documentation.
        """
        # Step 1: Always run static analyzers first
        print("Running static analysis...")
        content = self._run_static_analysis(repo_path)

        # Add metadata header
        line_count = len(content.splitlines())
        header = _build_metadata_header(repo_path, deep, line_count)
        content = header + content

        _ = output_file.write_text(content)
        print(f"  ✓ Basic context written ({line_count} lines)")

        if not deep:
            return content

        # Step 2: Expand with AI (only if deep=True)
        print("\nExpanding with AI-powered deep analysis...")
        print("This will take several minutes...\n")
        return asyncio.run(self._expand_with_ai(repo_path, output_file))

    def _run_static_analysis(self, repo_path: Path) -> str:
        """Run all static analyzers and produce markdown."""
        results: list[AnalysisResult] = []

        for analyzer in self.analyzers:
            try:
                result = analyzer.analyze(repo_path)
                if result is not None:
                    results.append(result)
            except Exception as e:
                log.warn(f"{analyzer.__class__.__name__} failed: {e}")

        results.sort(key=lambda r: r.order)

        lines = [f"# {repo_path.name} Codebase Overview", ""]
        lines.append("_Auto-generated context for AI agents_\n")

        for result in results:
            lines.append(f"## {result.section_name}")
            lines.append("")
            lines.append(result.content)
            lines.append("")

        return "\n".join(lines)

    async def _expand_with_ai(self, repo_path: Path, output_file: Path) -> str:
        """Use Claude to expand basic context with deep details.

        Combines the generic deep prompt with any project-specific prompt found
        in agent-config/deep-prompt.md.
        """
        print(f"{'=' * 60}")
        print("Deep Context Generator")
        print(f"   Repository: {repo_path}")
        print(f"   Output: {output_file}")
        print(f"{'=' * 60}\n")

        print("Pass 1: Understand the codebase")
        print("Pass 2: Add deep API/entity/business logic details")
        print("Pass 3: Document patterns and guides\n")

        # Build the prompt: generic base + optional project-specific additions
        base_prompt = _GENERIC_DEEP_PROMPT.replace(_OUTPUT_FILE_PLACEHOLDER, str(output_file))

        custom_prompt = _load_custom_deep_prompt()
        if custom_prompt:
            print(f"   Loading custom prompt from {_CUSTOM_PROMPT_PATH}")
            prompt = base_prompt + "\n\n---\n\n# PROJECT-SPECIFIC INSTRUCTIONS\n\n" + custom_prompt
        else:
            print(f"   No custom prompt found at {_CUSTOM_PROMPT_PATH}")
            print("   Using generic deep prompt (see agent-config/deep-prompt.md.example)\n")
            prompt = base_prompt

        had_error = False
        try:
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    system_prompt={"type": "preset", "preset": "claude_code"},
                    allowed_tools=["Read", "Edit", "Glob", "Grep", "Bash"],
                    permission_mode="acceptEdits",
                    cwd=str(repo_path),
                    max_turns=400,
                ),
            ):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text = block.text.strip()
                            if text:
                                lines = text.split("\n")
                                preview = lines[0][:80] if lines else ""
                                if preview:
                                    print(f"  {preview}...")

                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        print(f"\nError: {message.result or message.subtype}")
                        had_error = True
                    else:
                        print("\nDeep analysis complete")
                    break  # Exit loop properly to allow generator cleanup

        except Exception as e:
            print(f"\nException: {e}")
            log.exception("Deep context generation failed")
            return ""

        if had_error:
            return ""

        if output_file.exists():
            return output_file.read_text()
        else:
            print("Warning: Output file not found")
            return ""
