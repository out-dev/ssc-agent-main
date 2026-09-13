"""Manage shared workspace files for coding and sandbox testing."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from agent_framework import FunctionTool, tool

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Manages file operations within a configured shared workspace directory."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_path = Path(root_dir).resolve()
        try:
            self.root_path.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning(
                "Could not create workspace directory: %s",
                self.root_path,
                exc_info=True,
            )

    def _resolve_path(self, rel_path: str) -> Path:
        """Resolve a relative path safely within the workspace boundary."""
        clean = rel_path.strip().replace("\\", "/")
        clean = clean.lstrip("/")
        resolved = (self.root_path / clean).resolve()
        if resolved != self.root_path and not resolved.is_relative_to(self.root_path):
            raise ValueError(
                f"Path traversal denied: '{rel_path}' resolves outside "
                f"workspace boundary '{self.root_path}'"
            )
        return resolved

    def write_file(self, path: str, content: str) -> str:
        """Write content to a file in the workspace."""
        try:
            target = self._resolve_path(path)
            if target == self.root_path:
                return "Error: Cannot write directly to workspace root directory as a file."
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            relative = target.relative_to(self.root_path).as_posix()
            return f"Successfully wrote {len(content)} characters to '{relative}'."
        except Exception as exc:
            logger.exception("Failed to write workspace file '%s'", path)
            return f"Error writing file '{path}': {exc}"

    def read_file(self, path: str) -> str:
        """Read text content of a file in the workspace."""
        try:
            target = self._resolve_path(path)
            if not target.exists():
                return f"Error: File '{path}' does not exist."
            if target.is_dir():
                return f"Error: '{path}' is a directory, not a file."
            return target.read_text(encoding="utf-8")
        except Exception as exc:
            logger.exception("Failed to read workspace file '%s'", path)
            return f"Error reading file '{path}': {exc}"

    def list_files(self, directory: str = "") -> str:
        """List files and subdirectories in the workspace or a subdirectory."""
        try:
            target = self._resolve_path(directory)
            if not target.exists():
                return f"Error: Directory '{directory}' does not exist."
            if not target.is_dir():
                return f"Error: '{directory}' is a file, not a directory."

            items: list[str] = []
            for item in sorted(target.rglob("*")):
                rel = item.relative_to(self.root_path).as_posix()
                if item.is_dir():
                    items.append(f"{rel}/")
                else:
                    items.append(rel)

            if not items:
                return f"Directory '{directory or '.'}' is empty."
            return "\n".join(items)
        except Exception as exc:
            logger.exception("Failed to list workspace files in '%s'", directory)
            return f"Error listing files in '{directory}': {exc}"

    def delete_file(self, path: str) -> str:
        """Delete a file or directory in the workspace."""
        try:
            target = self._resolve_path(path)
            if target == self.root_path:
                return "Error: Cannot delete workspace root directory."
            if not target.exists():
                return f"Error: '{path}' does not exist."

            relative = target.relative_to(self.root_path).as_posix()
            if target.is_dir():
                shutil.rmtree(target)
                return f"Successfully deleted directory '{relative}'."
            else:
                target.unlink()
                return f"Successfully deleted file '{relative}'."
        except Exception as exc:
            logger.exception("Failed to delete workspace item '%s'", path)
            return f"Error deleting '{path}': {exc}"

    def get_tools(self) -> list[FunctionTool]:
        """Return agent tools for workspace file manipulation."""

        @tool(
            description=(
                "Write or create a text file in the shared workspace. "
                "'path' is relative to the workspace root (e.g. 'Program.cs' or 'src/App.cs'). "
                "Parent directories are created automatically."
            )
        )
        def write_file(path: str, content: str) -> str:
            """Write text content to a file in the workspace."""
            return self.write_file(path, content)

        @tool(
            description=(
                "Read the contents of a file in the shared workspace. "
                "'path' is relative to the workspace root."
            )
        )
        def read_file(path: str) -> str:
            """Read content from a file in the workspace."""
            return self.read_file(path)

        @tool(
            description=(
                "List all files and folders in the shared workspace or a subdirectory. "
                "'directory' is relative to the workspace root (empty string for workspace root)."
            )
        )
        def list_files(directory: str = "") -> str:
            """List files in the workspace directory."""
            return self.list_files(directory)

        @tool(
            description=(
                "Delete a file or folder from the shared workspace. "
                "'path' is relative to the workspace root."
            )
        )
        def delete_file(path: str) -> str:
            """Delete a file or directory in the workspace."""
            return self.delete_file(path)

        return [write_file, read_file, list_files, delete_file]
