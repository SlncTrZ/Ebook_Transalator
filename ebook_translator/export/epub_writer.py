"""EPUB writer — rebuild .epub from translated chunks, preserving original CSS.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from ebook_translator.db.database import Database


async def export_epub(
    db: Database,
    book_id: int,
    original_path: str,
    output_path: str | None = None,
) -> str:
    """Rebuild translated .epub from database.

    Reads original .epub structure, replaces text content with translations
    from the database, and writes a new .epub file.

    Args:
        db: Database instance.
        book_id: Book ID in the database.
        original_path: Path to the original .epub file.
        output_path: Output path (default: original_stem + '_vn.epub').

    Returns:
        Path to the generated .epub file.
    """
    book = await db.get_book(book_id)
    if book is None:
        raise ValueError(f"Book {book_id} not found")
    if book.status != "done":
        raise ValueError(f"Book {book_id} not fully translated (status: {book.status})")

    # Read original epub for structure/CSS
    original = epub.read_epub(original_path)

    # Load all translated chunks
    db_con = db.conn
    cursor = await db_con.execute(
        "SELECT chapter_idx, paragraph_idx, original_text, translated_text "
        "FROM chunks WHERE book_id = ? AND status = 'done' "
        "ORDER BY chapter_idx, paragraph_idx",
        (book_id,),
    )
    rows = await cursor.fetchall()

    # Group translations by chapter_idx
    chapters_map: dict[int, dict[int, str]] = {}
    for row in rows:
        ch = row["chapter_idx"]
        para = row["paragraph_idx"]
        chapters_map.setdefault(ch, {})[para] = row["translated_text"]

    # Walk through original items and replace text
    chapter_index = 0
    for item in original.get_items():
        if item.get_type() == 9:  # ITEM_DOCUMENT
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(item.get_body_content(), "lxml")
            translations = chapters_map.get(chapter_index, {})
            for para_index, p in enumerate(
                soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"])
            ):
                if para_index in translations:
                    translated = translations[para_index]
                    new_tag = soup.new_tag(p.name)
                    new_tag.string = translated
                    p.replace_with(new_tag)
            item.set_content(soup.encode())
            chapter_index += 1

    # Write output
    if output_path is None:
        src = Path(original_path)
        output_path = str(src.parent / f"{src.stem}_vn{src.suffix}")

    epub.write_epub(output_path, original, {})
    return output_path
