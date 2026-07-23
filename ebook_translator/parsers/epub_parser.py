"""EPUB parser — uses ebooklib + BeautifulSoup.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""
from __future__ import annotations

from bs4 import BeautifulSoup
from ebooklib import epub

from .base import BaseParser, ParsedBook


class EpubParser(BaseParser):
    """Parse .epub files into chapters and paragraphs."""

    def parse(self, file_path: str) -> ParsedBook:
        book = epub.read_epub(file_path)
        parsed = ParsedBook()

        # Metadata
        parsed.title = str(book.get_metadata("DC", "title")[0][0]) if book.get_metadata("DC", "title") else ""
        author_list = book.get_metadata("DC", "creator")
        if author_list:
            parsed.author = str(author_list[0][0])
        parsed.raw_metadata = {"language": book.get_metadata("DC", "language")}

        # Content
        for item in book.get_items():
            if item.get_type() == 9:  # ITEM_DOCUMENT
                soup = BeautifulSoup(item.get_body_content(), "lxml")
                paragraphs = []
                for p in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"]):
                    text = p.get_text(strip=True)
                    if text:
                        paragraphs.append(text)
                if paragraphs:
                    parsed.chapters.append(paragraphs)

        return parsed
