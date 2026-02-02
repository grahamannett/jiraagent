from collections.abc import Iterator
from dataclasses import dataclass, field
from itertools import chain
from pathlib import Path


def _resolve_path(path: str) -> list[str]:
    """Resolve a path to a list of file paths.

    If path is a file, returns [path].
    If path is a directory, returns all .md and .txt files recursively.
    """
    p = Path(path)
    if p.is_file():
        return [str(p)]
    if p.is_dir():
        files = chain(p.rglob("*.md"), p.rglob("*.txt"))
        return [str(f) for f in files]
    return []


@dataclass
class _ContextFile:
    file_path: str

    @property
    def text(self) -> str:
        with open(self.file_path, "r") as file:
            return file.read()


@dataclass
class ContextInfo:
    """
    should use filesystem tools instead of this implementation?
    https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem

    usage is for `uv run jira-agent run PROJ-123 --info.file <file_path>` in comparison
    to `uv run jira-agent run PROJ-123 --info <text>`
    """

    file_path: str | list[str] = field(default_factory=list)

    def __post_init__(self):
        paths = self.file_path if isinstance(self.file_path, list) else [self.file_path]
        resolved: list[str] = []

        for p in paths:
            resolved.extend(_resolve_path(p))

        self.file_path = resolved

    @property
    def files(self) -> Iterator[_ContextFile]:
        """Lazily yield file objects."""
        for fp in self.file_path:
            yield _ContextFile(fp)

    def __str__(self) -> str:
        return f"ContextInfo(file_path={self.file_path})"


if __name__ == "__main__":
    ci = ContextInfo(file_path="contexts/_ignore/inputs")
    print(f"Loading file(s): {ci}\n")
