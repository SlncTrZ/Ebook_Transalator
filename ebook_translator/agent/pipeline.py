"""Agentic Translation Pipeline — Research → Plan → Translate → Review.

Mỗi Agent là 1 LLM call riêng, có tư duy, có tools, có memory.
Không phải prompt injection — mỗi bước tự quyết định hành động.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from ebook_translator.db.database import Database
from ebook_translator.models import CacheEntry, Chunk, GlossaryEntry
from ebook_translator.agent.web_search import search_duckduckgo

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """Xuyên suốt pipeline — mỗi agent đọc/ghi vào context."""
    book_id: int = 0
    title: str = ""
    author: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
    category: str = "general"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"

    # Research phase
    book_summary: str = ""
    search_results: list[dict] = field(default_factory=list)
    glossary_terms: list[dict] = field(default_factory=list)  # [{"source": ..., "target": ...}]

    # Plan phase
    translation_strategy: str = ""
    style_notes: str = ""

    # Stats
    total_chunks: int = 0
    done_chunks: int = 0
    failed_chunks: int = 0


# ─── Tool: Gọi LLM ───────────────────────────────────────────────────────

async def _call_llm(
    messages: list[dict],
    ctx: AgentContext,
    response_format: dict | None = None,
    temperature: float = 0.3,
) -> str:
    """Gọi LLM với messages, trả về text response."""
    payload = {
        "model": ctx.model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{ctx.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {ctx.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


# ─── Agent 1: Research Agent ─────────────────────────────────────────────

RESEARCH_SYSTEM = """You are a Research Agent for a literary translation system.

Your job:
1. Analyze the book excerpt carefully
2. Decide if you need to search the web for more information about this book/author
3. If searched, incorporate the results
4. Return a JSON with:
   - title_original: original book title
   - title_localized: Vietnamese translation of the title
   - author: author name (in Vietnamese form if known)
   - source_lang: language code
   - target_lang: language code (default: vi)
   - category: van_hoc | lich_su | hien_dai | tien_hiep | general
   - summary: brief summary of the book in Vietnamese (max 200 chars)
   - style_notes: notes about writing style, tone, genre conventions
   - needs_more_search: true if you need more information
   - search_query: what to search next (empty if not needed)
   - confidence: 0.0-1.0 how confident you are about the metadata
   - glossary_suggestions: list of {"source": "...", "target": "..."} for key terms/names

THINK step by step:
1. Do I recognize this book? → set confidence high, explain
2. Do I need web search? → set needs_more_search
3. What terms need glossary entries? (character names, skills, items, techniques)
"""


async def research_agent(preview: str, ctx: AgentContext) -> AgentContext:
    """Research Agent: phân tích sách, search nếu cần, đề xuất metadata + glossary."""
    logger.info("[Research Agent] Starting research for book %d", ctx.book_id)

    user = f"[Book Excerpt - first {2000} chars]\n{preview[:2000]}\n\n"
    if ctx.search_results:
        user += "[Previous Search Results]\n"
        for r in ctx.search_results[-3:]:
            user += f"- {r.get('title', '')}: {r.get('content', '')[:300]}\n"

    user += "\nThink step by step. Return JSON now."

    messages = [
        {"role": "system", "content": RESEARCH_SYSTEM},
        {"role": "user", "content": user},
    ]

    raw = await _call_llm(messages, ctx, response_format={"type": "json_object"}, temperature=0.2)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[Research Agent] Non-JSON response: %s", raw[:200])
        return ctx

    ctx.title = parsed.get("title_original", ctx.title)
    ctx.author = parsed.get("author", ctx.author)
    ctx.source_lang = parsed.get("source_lang", ctx.source_lang)
    ctx.category = parsed.get("category", ctx.category)
    ctx.book_summary = parsed.get("summary", "")
    ctx.style_notes = parsed.get("style_notes", "")
    ctx.translation_strategy = ctx.style_notes

    # Glossary suggestions
    for term in parsed.get("glossary_suggestions", []):
        if term.get("source") and term.get("target"):
            ctx.glossary_terms.append(term)

    needs_more = parsed.get("needs_more_search", False)
    search_query = parsed.get("search_query", "")

    # Re-search nếu cần
    if needs_more and search_query:
        logger.info("[Research Agent] Re-searching: %s", search_query)
        try:
            results = await search_duckduckgo(search_query, max_results=5)
            ctx.search_results.extend(results)
            logger.info("[Research Agent] Got %d more results", len(results))

            # Phân tích kết quả search lần 2
            user2 = f"[Additional Search Results for: {search_query}]\n"
            for r in results[:3]:
                user2 += f"- {r.get('title', '')}: {r.get('content', '')[:300]}\n"
            user2 += "\n[Previous Analysis]\n"
            user2 += f"Title: {ctx.title}, Author: {ctx.author}\n"
            user2 += "Based on these new results, update the metadata if needed. Return updated JSON."

            messages2 = [
                {"role": "system", "content": "You are a research analyst. Update the book metadata based on new search results. Return JSON with same fields."},
                {"role": "user", "content": user2},
            ]
            raw2 = await _call_llm(messages2, ctx, response_format={"type": "json_object"}, temperature=0.2)
            try:
                parsed2 = json.loads(raw2)
                ctx.title = parsed2.get("title_original", ctx.title)
                ctx.author = parsed2.get("author", ctx.author)
                ctx.book_summary = parsed2.get("summary", ctx.book_summary)
                for term in parsed2.get("glossary_suggestions", []):
                    if term.get("source") and term.get("target"):
                        ctx.glossary_terms.append(term)
            except json.JSONDecodeError:
                pass
        except Exception as e:
            logger.warning("[Research Agent] Re-search failed: %s", e)

    logger.info(
        "[Research Agent] Done: title=%s, author=%s, lang=%s->%s, terms=%d",
        ctx.title, ctx.author, ctx.source_lang, ctx.target_lang, len(ctx.glossary_terms),
    )
    return ctx


# ─── Agent 2: Translate Agent ────────────────────────────────────────────

TRANSLATE_SYSTEM = """You are a professional literary translator.

You have context about:
- The book's title, author, genre
- Key glossary terms that MUST be used exactly
- Style notes for the translation

Rules:
1. Use the provided glossary terms EXACTLY — capitalize first letter of each word for names/skills/items
2. Follow the style notes for tone and register
3. Preserve meaning, nuance, and cultural context
4. Return ONLY the translated text, no explanations or notes
5. If there are character names, keep them consistent with glossary
"""


async def translate_agent(
    chunk: Chunk,
    glossary: list[GlossaryEntry],
    ctx: AgentContext,
    db: Database,
) -> str:
    """Translate Agent: dịch 1 chunk với context đầy đủ."""

    # Kiểm tra cache trước
    cached = await db.get_cached(
        content_hash=chunk.content_hash,
        source=ctx.source_lang,
        target=ctx.target_lang,
        model=ctx.model,
    )
    if cached is not None:
        logger.info("[Translate Agent] Cache HIT %s", chunk.content_hash[:12])
        return cached

    # Build context
    context = f"[Book Info]\nTitle: {ctx.title}\nAuthor: {ctx.author}\nCategory: {ctx.category}\n"
    context += f"Source: {ctx.source_lang} -> Target: {ctx.target_lang}\n"
    if ctx.book_summary:
        context += f"Summary: {ctx.book_summary}\n"
    if ctx.style_notes:
        context += f"Style: {ctx.style_notes}\n"

    # Glossary
    if glossary:
        context += "\n[Glossary - USE THESE EXACTLY]\n"
        for g in glossary:
            context += f"- {g.source_term} -> {g.target_term}\n"
    if ctx.glossary_terms:
        for g in ctx.glossary_terms:
            context += f"- {g['source']} -> {g['target']}\n"

    context += f"\n[Text to Translate]\n{chunk.original_text}"

    messages = [
        {"role": "system", "content": TRANSLATE_SYSTEM},
        {"role": "user", "content": context},
    ]

    result = await _call_llm(messages, ctx, temperature=0.3)

    # Save cache
    cache_entry = CacheEntry(
        content_hash=chunk.content_hash,
        source_lang=ctx.source_lang,
        target_lang=ctx.target_lang,
        model=ctx.model,
        translated_text=result,
    )
    await db.set_cached(cache_entry)

    return result


# ─── Agent 3: Review Agent ───────────────────────────────────────────────

REVIEW_SYSTEM = """You are a Translation Review Agent.

Check the translated text for:
1. Consistency with glossary terms (were they used correctly?)
2. Grammar and fluency in Vietnamese
3. Proper capitalization of names/skills/items (first letter of each word)
4. Preserved meaning from original

If the translation is GOOD, return: {"verdict": "pass", "note": "..."}
If there are MINOR issues, return: {"verdict": "fix", "suggestion": "corrected text"}
If there are MAJOR issues, return: {"verdict": "fail", "reason": "..."}
"""


async def review_agent(
    original: str,
    translated: str,
    glossary: list[GlossaryEntry],
    ctx: AgentContext,
) -> str:
    """Review Agent: kiểm tra chất lượng bản dịch."""
    if not translated:
        return translated

    # Chỉ review nếu có glossary terms
    if not glossary and not ctx.glossary_terms:
        return translated

    context = f"[Original]\n{original}\n\n[Translated]\n{translated}\n\n"
    if glossary:
        context += "[Glossary Terms]\n"
        for g in glossary:
            context += f"- {g.source_term} -> {g.target_term}\n"
    for g in ctx.glossary_terms:
        context += f"- {g['source']} -> {g['target']}\n"

    context += "\nReview the translation. Return JSON verdict."

    messages = [
        {"role": "system", "content": REVIEW_SYSTEM},
        {"role": "user", "content": context},
    ]

    try:
        raw = await _call_llm(messages, ctx, response_format={"type": "json_object"}, temperature=0.1)
        verdict = json.loads(raw)
        if verdict.get("verdict") == "fix":
            suggestion = verdict.get("suggestion", "")
            if suggestion:
                logger.info("[Review Agent] Fixed translation: %s...", suggestion[:50])
                return suggestion
        elif verdict.get("verdict") == "fail":
            logger.warning("[Review Agent] Translation failed review: %s", verdict.get("reason", ""))
    except Exception:
        pass

    return translated


# ─── Full Agentic Pipeline ───────────────────────────────────────────────

async def run_agentic_pipeline(
    db: Database,
    book_id: int,
    ctx: AgentContext,
    chapter_start: int = 0,
    chapter_end: int = 99999,
    preview_text: str = "",
) -> None:
    """Chạy full agentic pipeline: Research → Translate → Review.

    Args:
        db: Database instance.
        book_id: Book ID.
        ctx: Agent context (sẽ được cập nhật qua các bước).
        chapter_start: Chapter bắt đầu.
        chapter_end: Chapter kết thúc.
        preview_text: Text preview cho Research Agent.
    """
    # ── Phase 1: Research ─────────────────────────────────────────────
    logger.info("=== PHASE 1: Research ===")
    ctx = await research_agent(preview_text, ctx)

    # Lưu glossary terms từ research vào DB
    for term in ctx.glossary_terms:
        existing = await db.get_glossary(book_id)
        if not any(g.source_term == term["source"] for g in existing):
            await db.conn.execute(
                "INSERT INTO glossary (book_id, source_term, target_term, notes) VALUES (?, ?, ?, 'auto')",
                (book_id, term["source"], term["target"]),
            )
    await db.conn.commit()

    # ── Phase 2: Translate + Review ──────────────────────────────────
    logger.info("=== PHASE 2: Translate + Review ===")

    pending = await db.get_pending_chunks(book_id)
    # Filter by chapter range
    if chapter_end < 99999 or chapter_start > 0:
        pending = [c for c in pending if chapter_start <= c.chapter_idx + 1 <= chapter_end]

    ctx.total_chunks = len(pending)
    glossary = await db.get_glossary(book_id)

    for idx, chunk in enumerate(pending):
        try:
            # Translate
            translated = await translate_agent(chunk, glossary, ctx, db)

            # Review
            reviewed = await review_agent(chunk.original_text, translated, glossary, ctx)

            if chunk.id is not None:
                await db.update_chunk_result(chunk.id, reviewed, "done")
                ctx.done_chunks += 1

            if (idx + 1) % 10 == 0:
                logger.info("[Pipeline] %d/%d chunks done", idx + 1, ctx.total_chunks)

        except Exception as e:
            logger.error("[Pipeline] Chunk %d failed: %s", idx, e)
            if chunk.id is not None:
                await db.mark_chunk_failed(chunk.id, str(e))
                ctx.failed_chunks += 1

    await db.update_book_status(book_id)
    logger.info(
        "=== PIPELINE COMPLETE: %d/%d done, %d failed ===",
        ctx.done_chunks, ctx.total_chunks, ctx.failed_chunks,
    )
