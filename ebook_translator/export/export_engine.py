"""Export engine — xuất file .txt, .epub với nhiều chế độ.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from ebook_translator.db.database import Database


async def export_book(
    db: Database,
    book_id: int,
    output_path: str,
    mode: str = "translated",
    format: str = "txt",
    chapter_start: int = 1,
    chapter_end: int = 99999,
) -> str:
    """Export sách đã dịch.

    Args:
        db: Database instance.
        book_id: Book ID.
        output_path: Đường dẫn file xuất.
        mode: 'translated' (chỉ bản dịch) | 'bilingual' (song ngữ).
        format: 'txt' | 'epub'.
        chapter_start: Chapter bắt đầu.
        chapter_end: Chapter kết thúc.

    Returns:
        Đường dẫn file đã xuất.
    """
    book = await db.get_book(book_id)
    if book is None:
        raise ValueError(f"Book {book_id} not found")

    # Lấy chunks đã dịch
    cursor = await db.conn.execute(
        "SELECT chapter_idx, paragraph_idx, original_text, translated_text, status "
        "FROM chunks WHERE book_id = ? AND status = 'done' "
        "AND chapter_idx + 1 >= ? AND chapter_idx + 1 <= ? "
        "ORDER BY chapter_idx, paragraph_idx",
        (book_id, chapter_start, chapter_end),
    )
    rows = await cursor.fetchall()
    if not rows:
        raise ValueError("No translated chunks found in this range")

    # Nhóm theo chapter
    chapters: dict[int, list[dict]] = {}
    for r in rows:
        ch = r["chapter_idx"]
        chapters.setdefault(ch, []).append(dict(r))

    if format == "epub":
        if Path(book.file_path).suffix.lower() == ".epub" and Path(book.file_path).exists():
            return await _export_epub_preserving_source(book, chapters, output_path, mode)
        return await _export_epub(book, chapters, output_path, mode)
    else:
        return await _export_txt(book, chapters, output_path, mode)


async def _export_txt(
    book,
    chapters: dict[int, list],
    output_path: str,
    mode: str,
) -> str:
    """Xuất .txt."""
    lines: list[str] = []
    lines.append(f"Title: {book.title}")
    lines.append(f"Author: {book.author}")
    lines.append(f"Source: {book.source_lang} -> {book.target_lang}")
    lines.append("=" * 60)
    lines.append("")

    for ch_idx in sorted(chapters.keys()):
        lines.append(f"\n--- Chapter {ch_idx + 1} ---\n")
        for chunk in chapters[ch_idx]:
            if mode == "bilingual":
                lines.append(f"[Original]\n{chunk['original_text']}\n")
                lines.append(f"[Translated]\n{chunk['translated_text']}\n")
                lines.append("---")
            else:
                lines.append(chunk["translated_text"])
            lines.append("")

    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise ValueError(f"Cannot create output directory: {e}") from e
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except OSError as e:
        raise ValueError(f"Cannot write output file: {e}") from e
    return output_path


async def _export_epub_preserving_source(
    book,
    chapters: dict[int, list],
    output_path: str,
    mode: str,
) -> str:
    """Patch only source XHTML entries; preserve all other EPUB bytes/metadata."""
    from copy import copy
    from pathlib import PurePosixPath
    from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile
    from xml.etree import ElementTree

    from bs4 import BeautifulSoup
    from ebooklib import ITEM_DOCUMENT, epub

    source_book = epub.read_epub(book.file_path)
    replacements: dict[str, bytes] = {}

    with ZipFile(book.file_path, "r") as source_zip:
        container = ElementTree.fromstring(source_zip.read("META-INF/container.xml"))
        rootfile = next(
            element
            for element in container.iter()
            if element.tag.rsplit("}", 1)[-1] == "rootfile"
        )
        opf_path = PurePosixPath(rootfile.attrib["full-path"])
        content_root = opf_path.parent

        chapter_idx = 0
        for item in source_book.get_items():
            if item.get_type() != ITEM_DOCUMENT:
                continue

            soup = BeautifulSoup(item.get_content(), "lxml")
            elements = soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"])
            source_elements = [element for element in elements if element.get_text(strip=True)]
            if not source_elements:
                continue

            translated_chunks = chapters.get(chapter_idx, [])
            by_paragraph = {chunk["paragraph_idx"]: chunk for chunk in translated_chunks}
            for paragraph_idx, element in enumerate(source_elements):
                chunk = by_paragraph.get(paragraph_idx)
                if not chunk:
                    continue
                translated = chunk["translated_text"] or ""
                if mode == "bilingual":
                    translated_tag = soup.new_tag("p")
                    translated_tag["class"] = ["ebook-translator-translation"]
                    translated_tag.string = translated
                    element.insert_after(translated_tag)
                else:
                    element.clear()
                    element.string = translated

            internal_path = str(content_root / PurePosixPath(item.file_name))
            replacements[internal_path] = str(soup).encode("utf-8")
            chapter_idx += 1

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output_path, "w") as output_zip:
            for info in source_zip.infolist():
                data = replacements.get(info.filename, source_zip.read(info.filename))
                cloned = copy(info)
                if info.filename == "mimetype":
                    cloned.compress_type = ZIP_STORED
                elif cloned.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                    cloned.compress_type = ZIP_DEFLATED
                output_zip.writestr(cloned, data)

    return output_path


async def _export_epub(
    book,
    chapters: dict[int, list],
    output_path: str,
    mode: str,
) -> str:
    """Xuất .epub."""
    from ebooklib import epub

    ep = epub.EpubBook()
    ep.set_identifier(str(book.id))
    ep.set_title(f"{book.title} ({book.target_lang})")
    ep.set_language(book.target_lang or "vi")

    if book.author:
        ep.add_author(book.author)

    all_items: list = []
    toc_links: list = []

    for ch_idx in sorted(chapters.keys()):
        content_parts: list[str] = []
        content_parts.append(f"<h1>Chapter {ch_idx + 1}</h1>")

        for chunk in chapters[ch_idx]:
            if mode == "bilingual":
                content_parts.append(
                    f"<p style='color:#888;font-style:italic'>{escape(chunk['original_text'])}</p>"
                )
                content_parts.append(f"<p>{escape(chunk['translated_text'] or '')}</p>")
                content_parts.append("<hr/>")
            else:
                content_parts.append(f"<p>{escape(chunk['translated_text'] or '')}</p>")

        chap = epub.EpubHtml(
            title=f"Chapter {ch_idx + 1}",
            file_name=f"chap_{ch_idx + 1}.xhtml",
            lang=book.target_lang or "vi",
        )
        chap.content = "<html><body>" + "".join(content_parts) + "</body></html>"
        ep.add_item(chap)
        all_items.append(chap)
        toc_links.append(
            epub.Link(
                f"chap_{ch_idx + 1}.xhtml", f"Chapter {ch_idx + 1}", f"ch{ch_idx + 1}"
            )
        )

    ep.toc = toc_links
    ep.add_item(epub.EpubNcx())
    ep.add_item(epub.EpubNav())
    ep.spine = ["nav"] + all_items

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(output_path, ep, {})
    return output_path
