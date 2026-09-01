"""Model boundary normalization tests."""

from ebook_translator.models import Book, BookCategory


def test_book_category_string_is_normalized_to_enum() -> None:
    book = Book(category=BookCategory.SCI_FI.value)
    assert book.category is BookCategory.SCI_FI


def test_unknown_book_category_falls_back_to_general() -> None:
    book = Book(category="unknown-category")
    assert book.category is BookCategory.GENERAL
