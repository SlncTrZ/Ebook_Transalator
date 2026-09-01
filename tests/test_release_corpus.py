"""Release-corpus and scale smoke tests for v1.0 hardening."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from ebooklib import ITEM_DOCUMENT, ITEM_IMAGE, epub

from ebook_translator.db.database import Database
from ebook_translator.export.export_engine import export_book
from ebook_translator.models import Book, Chunk
from ebook_translator.parsers.epub_parser import EpubParser
from ebook_translator.utils.chunker import chunk_book


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63606060f80f0001040100b51c0c020000000049454e44ae426082"
)


def _build_complex_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("release-corpus-001")
    book.set_title("星海纪事 — Édition annotée")
    book.set_language("zh")
    book.add_author("林舟 / Lin Zhou")
    book.add_metadata("DC", "description", "多语言 metadata / corpus validation")

    css = epub.EpubItem(
        uid="style-main",
        file_name="styles/main.css",
        media_type="text/css",
        content=b"body{font-family:serif}.accent{font-weight:700}img{max-width:100%}",
    )
    image = epub.EpubItem(
        uid="cover-art",
        file_name="assets/cover-image.png",
        media_type="image/png",
        content=PNG_1X1,
    )
    book.add_item(css)
    book.add_item(image)

    ch1 = epub.EpubHtml(
        title="第一章 / Opening",
        file_name="Text/part-001-opening.xhtml",
        lang="zh",
    )
    ch1.content = (
        "<html><head></head><body>"
        "<h1>第一章 星海</h1>"
        "<p class='accent'>舰桥报告：反应堆有 12 个模块。</p>"
        "<p>第二段包含中文标点。没有空格！仍然应该保持顺序？</p>"
        "<img src='../assets/cover-image.png' alt='cover'/>"
        "</body></html>"
    )
    ch1.add_item(css)

    ch2 = epub.EpubHtml(
        title="Chapitre Deux",
        file_name="Text/odd.chapter-name_02.xhtml",
        lang="fr",
    )
    ch2.content = (
        "<html><head></head><body>"
        "<h2>Chapitre Deux</h2>"
        "<p>Café déjà vu — résumé numéro 27.</p>"
        "<p>Final paragraph for nested navigation.</p>"
        "</body></html>"
    )
    ch2.add_item(css)

    book.add_item(ch1)
    book.add_item(ch2)
    book.toc = ((epub.Section("Partie I / 第一部"), (ch1, ch2)),)
    book.spine = ["nav", ch1, ch2]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book)


@pytest.mark.asyncio
async def test_complex_epub_round_trip_preserves_non_document_resources(tmp_path: Path) -> None:
    source = tmp_path / "complex-source.epub"
    output = tmp_path / "complex-translated.epub"
    _build_complex_epub(source)

    parsed = EpubParser().parse(str(source))
    assert parsed.title == "星海纪事 — Édition annotée"
    assert parsed.author == "林舟 / Lin Zhou"
    assert len(parsed.chapters) >= 2

    database = Database(tmp_path / "complex.db")
    await database.connect()
    book_id = await database.insert_book(
        Book(
            file_path=str(source),
            title=parsed.title,
            author=parsed.author,
            source_lang="zh",
            target_lang="vi",
        )
    )
    chunks = chunk_book(book_id, parsed.chapters)
    await database.insert_chunks(chunks)

    cursor = await database.conn.execute(
        "SELECT id, original_text FROM chunks WHERE book_id = ? "
        "ORDER BY chapter_idx, paragraph_idx, segment_idx",
        (book_id,),
    )
    rows = await cursor.fetchall()
    for row in rows:
        await database.update_chunk_result(
            row["id"], f"VI::{row['original_text']}", "done"
        )

    await export_book(database, book_id, str(output), format="epub")

    with zipfile.ZipFile(source) as src_zip, zipfile.ZipFile(output) as out_zip:
        src_names = set(src_zip.namelist())
        out_names = set(out_zip.namelist())
        assert src_names == out_names
        for name in src_names:
            if name.endswith((".xhtml", ".html", ".htm")):
                continue
            assert out_zip.read(name) == src_zip.read(name), name

    reopened = epub.read_epub(str(output))
    assert reopened.get_metadata("DC", "title")[0][0] == "星海纪事 — Édition annotée"
    assert reopened.get_metadata("DC", "creator")[0][0] == "林舟 / Lin Zhou"
    images = [item for item in reopened.get_items() if item.get_type() == ITEM_IMAGE]
    assert any(item.file_name.endswith("assets/cover-image.png") for item in images)
    documents = [item for item in reopened.get_items() if item.get_type() == ITEM_DOCUMENT]
    translated_document_text = b"\n".join(item.get_content() for item in documents)
    assert "VI::".encode() in translated_document_text

    await database.close()


@pytest.mark.asyncio
async def test_large_book_progress_and_resume_scope_remain_deterministic(tmp_path: Path) -> None:
    database = Database(tmp_path / "large-book.db")
    await database.connect()
    book_id = await database.insert_book(Book(file_path="large.txt", title="Large corpus"))

    chunks: list[Chunk] = []
    for chapter_idx in range(50):
        for paragraph_idx in range(50):
            chunks.append(
                Chunk(
                    book_id=book_id,
                    chapter_idx=chapter_idx,
                    paragraph_idx=paragraph_idx,
                    segment_idx=0,
                    content_hash=f"large-{chapter_idx}-{paragraph_idx}",
                    original_text=f"Chapter {chapter_idx + 1}, paragraph {paragraph_idx + 1}",
                )
            )
    assert len(chunks) == 2500
    await database.insert_chunks(chunks)

    cursor = await database.conn.execute(
        "SELECT id, chapter_idx, paragraph_idx FROM chunks WHERE book_id = ? "
        "ORDER BY chapter_idx, paragraph_idx, segment_idx",
        (book_id,),
    )
    rows = await cursor.fetchall()
    for index, row in enumerate(rows):
        if index % 7 == 0:
            await database.update_chunk_result(row["id"], "done", "done")
        elif index % 113 == 0:
            await database.mark_chunk_failed(row["id"], "synthetic transient failure")

    whole = await database.get_chunk_progress(book_id)
    assert whole["total"] == 2500
    assert whole["done"] + whole["failed"] + whole["pending"] == 2500

    job_id = await database.create_translation_job(
        book_id,
        "standard",
        "ollama",
        "release-model",
        11,
        20,
    )
    await database.transition_translation_job(job_id, "interrupted", "release corpus restart")
    plan = await database.get_job_resume_plan(job_id)

    assert plan["progress"]["total"] == 500
    assert all(10 <= chunk.chapter_idx <= 19 for chunk in plan["remaining_chunks"])
    assert all(chunk.status in {"pending", "failed"} for chunk in plan["remaining_chunks"])
    remaining_ids = {chunk.id for chunk in plan["remaining_chunks"]}
    done_cursor = await database.conn.execute(
        "SELECT id FROM chunks WHERE book_id = ? AND chapter_idx BETWEEN 10 AND 19 AND status = 'done'",
        (book_id,),
    )
    done_ids = {row["id"] for row in await done_cursor.fetchall()}
    assert remaining_ids.isdisjoint(done_ids)

    resumed = await database.resume_translation_job(job_id)
    assert resumed["job"]["status"] == "running"
    assert resumed["job"]["resume_count"] == 1
    await database.close()
