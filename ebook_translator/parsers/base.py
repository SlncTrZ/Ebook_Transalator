"""Base parser interface — all parsers implement this.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedBook:
    """Normalized output from any parser."""

    title: str = ""
    author: str = ""
    chapters: list[list[str]] = field(default_factory=list)
    # chapters = list of chapters, each chapter = list of paragraphs
    raw_metadata: dict = field(default_factory=dict)


class BaseParser(ABC):
    """Abstract parser — subclass for each format."""

    @abstractmethod
    def parse(self, file_path: str) -> ParsedBook:
        """Parse file and return normalized structure."""
        ...
