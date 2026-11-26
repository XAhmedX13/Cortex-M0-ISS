"""Error collection and formatting for the Thumb assembler."""

import sys
from typing import List

MAX_ERRORS = 50


class AsmError(Exception):
    """One assembler diagnostic with a source location."""

    def __init__(self, file: str, line: int, message: str) -> None:
        """Store the location and pre-format the diagnostic text."""
        super().__init__(f"{file}:{line}: error: {message}")
        self.file = file
        self.line = line
        self.message = message


class ErrorCollector:
    """Collect diagnostics so a run can report many errors at once."""

    def __init__(self) -> None:
        """Start with empty error and warning lists."""
        self.errors: List[AsmError] = []
        self.warnings: List[str] = []

    def add_error(self, file: str, line: int, message: str) -> None:
        """Record an error, ignoring any after the first 50."""
        if len(self.errors) < MAX_ERRORS:
            self.errors.append(AsmError(file, line, message))

    def add_warning(self, file: str, line: int, message: str) -> None:
        """Record a non-fatal warning in the same format."""
        self.warnings.append(f"{file}:{line}: warning: {message}")

    def has_errors(self) -> bool:
        """Return True if at least one error was collected."""
        return len(self.errors) > 0

    def report(self) -> None:
        """Print warnings then errors to stderr."""
        for warning in self.warnings:
            print(warning, file=sys.stderr)
        for error in self.errors:
            print(error, file=sys.stderr)
