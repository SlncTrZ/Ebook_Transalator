"""P1 EPUB fidelity test: preserve source resources while replacing text."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from bs4 import BeautifulSoup
from ebooklib import ITEM_DOCUMENT, ITEM_STYLE, epub

from ebook_translator.db.database import Database
from ebook_translator.export.export_engine import export_book
from ebook_translator.models import Book, Chunk


@pytest_asyncio.fixture
async def epub_case(tmp_path: Path):
    source_path = tmp_path / "source.epub"
    output_path = tmp_path / "translated.epub"

    source = epub.EpubBook()
    source.set_identifier("fidelity-test")
    source.set_title("Styled Source")
    source.set_language("en")
    source.add_author("Example Author")

    css = epub.EpubItem(
        uid="style",
        file_name="style/main.css",
        media_type="text/css",
        content=b"p { color: #123456; }",
    )
    source.add_item(css)

    chapter = epub.EpubHtml(title="One", file_name="text/ch1.xhtml", lang="en")
    chapter.content = (
        "<html><head><link rel='stylesheet' href='../style/main.css'/></head>"
        "<body><h1>Heading</h1><p>First paragraph</p><p>Second paragraph</p></body></html>"
    )
    source.add_item(chapter)
    source.toc = [chapter]
    source.spine = ["nav", chapter]
    source.add_item(epub.EpubNcx())
    source.add_item(epub.EpubNav())
    epub.write_epub(str(source_path), source, {})

    database = Database(tmp_path / "fidelity.db")
    await database.connect()
    book_id = await database.insert_book(
        Book(file_path=str(source_path), title="Styled Source", author="Example Author")
    )
    await database.insert_chunks(
        [
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=0,
                content_hash="epub-h1",
                original_text="Heading",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=1,
                content_hash="epub-p1",
                original_text="First paragraph",
            ),
            Chunk(
                book_id=book_id,
                chapter_idx=0,
                paragraph_idx=2,
                content_hash="epub-p2",
                original_text="Second paragraph",
            ),
        ]
    )
    cursor = await database.conn.execute(
        "SELECT id FROM chunks WHERE book_id = ? ORDER BY paragraph_idx", (book_id,)
    )
    ids = [row["id"] for row in await cursor.fetchall()]
    for chunk_id, text in zip(ids, ["Tiêu đề", "Đoạn một", "Đoạn hai"], strict=True):
        await database.update_chunk_result(chunk_id, text, "done")

    yield database, book_id, output_path
    await database.close()


@pytest.mark.asyncio
async def test_epub_export_preserves_css_and_document_structure(epub_case) -> None:
    database, book_id, output_path = epub_case

    await export_book(database, book_id, str(output_path), format="epub")

    result = epub.read_epub(str(output_path))
    styles = [item for item in result.get_items() if item.get_type() == ITEM_STYLE]
    assert any(b"#123456" in item.get_content() for item in styles)

    documents = [item for item in result.get_items() if item.get_type() == ITEM_DOCUMENT]
    chapter = next(item for item in documents if item.file_name.endswith("ch1.xhtml"))
    soup = BeautifulSoup(chapter.get_content(), "lxml")
    assert soup.find("h1").get_text(strip=True) == "Tiêu đề"
    assert [p.get_text(strip=True) for p in soup.find_all("p")][:2] == ["Đoạn một", "Đoạn hai"]
