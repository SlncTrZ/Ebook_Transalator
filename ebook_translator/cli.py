"""CLI entry point — click-based command line interface.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from ebook_translator.db.database import Database
from ebook_translator.export.epub_writer import export_epub
from ebook_translator.models import Book, BookCategory
from ebook_translator.parsers.epub_parser import EpubParser
from ebook_translator.parsers.txt_parser import TxtParser
from ebook_translator.translator.pipeline import TranslationConfig, TranslationPipeline
from ebook_translator.utils.chunker import chunk_book

console = Console()

# Supported file extensions → parser mapping
PARSERS = {
    ".epub": EpubParser(),
    ".txt": TxtParser(),
}


def _get_parser(file_path: str) -> EpubParser | TxtParser | None:
    ext = Path(file_path).suffix.lower()
    parser = PARSERS.get(ext)
    if parser is None:
        supported = ", ".join(PARSERS)
        console.print(f"[red]Unsupported format '{ext}'. Supported: {supported}[/red]")
    return parser


async def _translate_flow(
    file_path: str,
    api_key: str,
    model: str,
    source_lang: str,
    target_lang: str,
    category: str,
    db_path: str | None,
) -> None:
    """Full async translation pipeline: parse → chunk → translate → export."""
    db = Database(db_path)
    await db.connect()

    try:
        # 1. Parse
        console.print(f"[blue]📖 Parsing:[/blue] {file_path}")
        parser = _get_parser(file_path)
        if parser is None:
            return
        parsed = parser.parse(file_path)
        total_paragraphs = sum(len(ch) for ch in parsed.chapters)
        console.print(f"  Title: {parsed.title or 'Unknown'}")
        console.print(f"  Author: {parsed.author or 'Unknown'}")
        console.print(
            f"  Chapters: {len(parsed.chapters)}, Paragraphs: {total_paragraphs}"
        )

        # 2. Insert book
        book = Book(
            file_path=file_path,
            title=parsed.title,
            author=parsed.author,
            source_lang=source_lang,
            target_lang=target_lang,
            category=BookCategory(category) if category else BookCategory.GENERAL,
        )
        book_id = await db.insert_book(book)

        # 3. Chunk
        console.print("[blue]🔪 Chunking...[/blue]")
        chunks = chunk_book(book_id, parsed.chapters)
        book.total_chunks = len(chunks)
        await db.insert_chunks(chunks)
        console.print(f"  Created {len(chunks)} chunks")

        # 4. Translate
        config = TranslationConfig(
            api_key=api_key,
            model=model,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        pipeline = TranslationPipeline(db, config)

        console.print(f"[green]🌐 Translating {len(chunks)} chunks...[/green]")
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Translating...", total=len(chunks))
            pending = await db.get_pending_chunks(book_id)
            glossary = await db.get_glossary(book_id)

            for chunk in pending:
                try:
                    translated = await pipeline.translate_chunk(chunk, glossary)
                    if chunk.id is not None:
                        await db.update_chunk_result(chunk.id, translated, "done")
                except Exception as e:
                    if chunk.id is not None:
                        await db.mark_chunk_failed(chunk.id, str(e))
                    console.print(f"[red]  ✗ Chunk failed: {e}[/red]")
                progress.advance(task)

            await db.update_book_status(book_id)

        # 5. Export
        book_status = await db.get_book(book_id)
        if book_status and book_status.status == "done":
            output = await export_epub(db, book_id, file_path)
            console.print(f"[green]✅ Exported:[/green] {output}")
        else:
            console.print(
                f"[yellow]⚠️  Book status: {book_status.status if book_status else 'unknown'}. "
                "Export skipped — some chunks failed.[/yellow]"
            )

    finally:
        await db.close()


@click.group()
def cli() -> None:
    """Ebook Translator — CLI tool for automated ebook translation."""


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--api-key",
    envvar="OPENAI_API_KEY",
    required=True,
    help="OpenAI API key (or OPENAI_API_KEY env)",
)
@click.option("--model", default="gpt-4o-mini", help="Model name")
@click.option("--source-lang", default="en", help="Source language code")
@click.option("--target-lang", default="vi", help="Target language code")
@click.option("--category", default="general", help="Book category for prompt routing")
@click.option("--db-path", default=None, help="Custom database path")
def translate(
    file: str,
    api_key: str,
    model: str,
    source_lang: str,
    target_lang: str,
    category: str,
    db_path: str | None,
) -> None:
    """Translate an ebook file from source to target language."""
    logging.basicConfig(
        level=logging.INFO,
        handlers=[RichHandler(rich_tracebacks=True, console=console)],
        format="%(message)s",
    )
    asyncio.run(
        _translate_flow(
            file, api_key, model, source_lang, target_lang, category, db_path
        )
    )


@cli.command()
@click.option("--db-path", default=None, help="Custom database path")
@click.option("--purge", is_flag=True, help="Clear entire cache")
def cache(db_path: str | None, purge: bool) -> None:
    """Manage translation cache."""

    async def _run() -> None:
        db = Database(db_path)
        await db.connect()
        try:
            if purge:
                await db.conn.execute("DELETE FROM cache")
                await db.conn.commit()
                console.print("[green]Cache cleared.[/green]")
            else:
                cursor = await db.conn.execute("SELECT COUNT(*) as cnt FROM cache")
                row = await cursor.fetchone()
                console.print(f"Cache entries: {row['cnt'] if row else 0}")
        finally:
            await db.close()

    asyncio.run(_run())


if __name__ == "__main__":
    cli()
