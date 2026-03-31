"""Change detection for targeted evaluation.

Maps changed files (from git diff or change-context documents) to
interface identifiers using the descriptor's file-interface mappings.
This enables the orchestrator to focus evaluation on interfaces
affected by recent code changes.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

from evaluation.gen_eval.descriptor import InterfaceDescriptor


class ChangeDetector:
    """Detect which interfaces changed for targeted evaluation."""

    def __init__(self, descriptor: InterfaceDescriptor) -> None:
        self.descriptor = descriptor

    def detect_from_git_diff(self, base_ref: str = "main") -> list[str]:
        """Parse ``git diff --name-only <ref>`` output and map changed files
        to interface endpoints using the descriptor's file_interface_map.

        Falls back to empty list if git diff fails or no mappings match.
        """
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []
            changed_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except (subprocess.SubprocessError, OSError):
            return []

        return self._map_files_to_interfaces(changed_files)

    def detect_from_change_context(self, change_context_path: Path) -> list[str]:
        """Read change-context.md to identify affected interfaces.

        Looks for lines that match file patterns in the descriptor's
        file_interface_map. Falls back to empty list if file is absent.
        """
        try:
            text = change_context_path.read_text()
        except (FileNotFoundError, OSError):
            return []

        # Extract potential file paths from the document.
        # Look for backtick-quoted paths and bare tokens that look like paths.
        candidates: list[str] = []
        for line in text.splitlines():
            # Extract backtick-quoted references first
            for match in re.findall(r"`([^`]+)`", line):
                candidates.append(match.strip())
            # Also try splitting the line into tokens
            for token in line.split():
                token = token.strip("`-*[] ")
                if ("/" in token or "." in token) and token not in candidates:
                    candidates.append(token)

        return self._map_files_to_interfaces(candidates)

    def _map_files_to_interfaces(self, files: list[str]) -> list[str]:
        """Match a list of file paths against descriptor file_interface_map patterns."""
        matched: set[str] = set()
        for mapping in self.descriptor.file_interface_map:
            pattern = mapping.file_pattern
            for filepath in files:
                if fnmatch.fnmatch(filepath, pattern):
                    matched.update(mapping.interfaces)
        return sorted(matched)
