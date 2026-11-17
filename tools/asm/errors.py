"""Error objects and collection for the Thumb assembler."""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AsmError(Exception):
    """An assembler error tied to a source line when one is available."""

    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    source: Optional[str] = None

    def format(self) -> str:
        """Return the required ``file:line: error: message`` style string."""
        text = ""
        if self.file is not None:
            text += str(self.file)
        if self.line is not None:
            text += (":" if text else "") + str(self.line)
        if text:
            text += ": "
        text += "error: " + self.message
        return text

    def __str__(self) -> str:
        """Return the formatted diagnostic when the exception is printed."""
        return self.format()


class Diagnostics:
    """Store assembler errors and warnings in source order."""

    def __init__(self, limit: int = 50) -> None:
        """Create an empty diagnostic list with a cap on reported messages."""
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.limit = limit

    def add_error(self, error: AsmError) -> None:
        """Add an error unless the reporting limit has been reached."""
        if len(self.errors) < self.limit:
            self.errors.append(error.format())

    def error(self, message: str, statement=None) -> None:
        """Build and add an error from a message and source statement."""
        self.add_error(make_error(message, statement))

    def add_warning(self, warning: AsmError) -> None:
        """Add a warning unless the reporting limit has been reached."""
        if len(self.warnings) < self.limit:
            text = warning.format()
            self.warnings.append(text.replace(": error: ", ": warning: ", 1))

    def warning(self, message: str, statement=None) -> None:
        """Build and add a warning from a message and source statement."""
        self.add_warning(make_error(message, statement))

    def has_errors(self) -> bool:
        """Return True when at least one error was reported."""
        return bool(self.errors)

    def print_all(self, stream) -> None:
        """Print warnings first, then errors, to the supplied text stream."""
        for text in self.warnings:
            print(text, file=stream)
        for text in self.errors:
            print(text, file=stream)


def make_error(message: str, statement=None) -> AsmError:
    """Create an error using the file, line and text of a statement."""
    if statement is None:
        return AsmError(message)
    return AsmError(message, statement.file, statement.line, statement.source)
