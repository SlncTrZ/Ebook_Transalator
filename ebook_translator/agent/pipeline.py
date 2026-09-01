"""Agentic Translation Pipeline — Research → HITL → Translate → Validate (Deterministic).

Thiết kế:
1. Research Agent: 1 lần duy nhất trên preview → sinh metadata + glossary → DỪNG, chờ user duyệt
2. Translate Agent: Dịch từng chunk với context + cache fingerprinting
3. Deterministic Validation: Regex check glossary terms, retry nếu thiếu (KHÔNG dùng AI)

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

from ebook_translator.db.database import Database
from ebook_translator.models import CacheEntry, Chunk, GlossaryEntry
from ebook_translator.agent.validator import check_glossary_terms, build_retry_prompt
from ebook_translator.translator.cache_key import prompt_fingerprint
from ebook_translator.translator.context import ContextBuilder
from ebook_translator.translator.gateway import LLMConfig, LLMGateway
from ebook_translator.translator.metrics import (
    record_cache_hit,
    record_translation_memory_hit,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # Số lần retry tối đa khi validation fail


@dataclass
class AgentContext:
    """Xuyên suốt pipeline."""

    book_id: int = 0
    title: str = ""
    localized_title: str = ""
    author: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
    category: str = "general"
    vendor: str = "openai"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = ""
    book_summary: str = ""
    search_results: list[dict] = field(default_factory=list)
    glossary_terms: list[dict] = field(default_factory=list)
    translation_strategy: str = ""
    style_notes: str = ""


# ─── Tool: Gọi LLM ───────────────────────────────────────────────────────


async def _call_llm(
    messages: list[dict],
    ctx: AgentContext,
    response_format: dict | None = None,
    temperature: float = 0.3,
) -> str:
    """Generate through the unified provider-agnostic LLM gateway."""
    gateway = LLMGateway(
        LLMConfig(
            vendor=ctx.vendor,
            api_key=ctx.api_key,
            model=ctx.model,
            base_url=ctx.base_url,
        )
    )
    return await gateway.generate(
        messages,
        temperature=temperature,
        response_format=response_format,
    )


# ─── Agent 1: Research Agent ─────────────────────────────────────────────

RESEARCH_SYSTEM = """You are a Research Agent. Analyze the book excerpt.
Return JSON with:
{
  "title_original": "original title in source language",
  "title_localized": "VIETNAMESE TRANSLATION of the title — this MUST be different from title_original, translated to Vietnamese",
  "author": "author name (Vietnamese form if known — translate Chinese names to Vietnamese)",
  "source_lang": "language code",
  "target_lang": "language code (default: vi)",
  "category": "van_hoc | lich_su | hien_dai | tien_hiep | general",
  "summary": "brief Vietnamese summary (max 200 chars)",
  "style_notes": "notes on writing style/tone",
  "needs_more_search": true/false,
  "search_query": "what to search next if needed",
  "confidence": 0.0-1.0,
  "glossary_suggestions": [{"source": "original term", "target": "Vietnamese translation"}]
}

IMPORTANT: title_localized MUST be Vietnamese, NOT the original language.
Example: title_original="San the" -> title_localized="Tam The"
Example: title_original="Hong Tran Ma Dao" -> title_localized="Hong Tran Ma Dao"
Example: title_original="The Lord of the Rings" -> title_localized="Chua Te cua nhung Chiec Nhan"
  "source_lang": "language code",
  "target_lang": "language code (default: vi)",
  "category": "van_hoc | lich_su | hien_dai | tien_hiep | general",
  "summary": "brief Vietnamese summary (max 200 chars)",
  "style_notes": "notes on writing style/tone",
  "needs_more_search": true/false,
  "search_query": "what to search next if needed",
  "confidence": 0.0-1.0,
  "glossary_suggestions": [{"source": "...", "target": "..."}]
}
THINK step by step before answering.
"""


async def research_agent(
    preview: str,
    ctx: AgentContext,
    user_feedback: str = "",
    force_search: bool = False,
) -> AgentContext:
    """Research Agent: analyze metadata and honor explicit HITL feedback/search requests."""
    logger.info("[Research] Starting for book %d", ctx.book_id)

    from ebook_translator.agent.web_search import search_duckduckgo

    user = f"[Book Excerpt]\n{preview[:2000]}\n"
    if user_feedback:
        user += f"\n[User Feedback]\n{user_feedback}\n"
    if force_search:
        user += "\nThe user explicitly requested web verification. Set needs_more_search=true.\n"
    user += "\nReturn JSON."
    messages = [
        {"role": "system", "content": RESEARCH_SYSTEM},
        {"role": "user", "content": user},
    ]
    raw = await _call_llm(
        messages, ctx, response_format={"type": "json_object"}, temperature=0.2
    )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("[Research] Non-JSON: %s — %s", raw[:200], e)
        return ctx

    ctx.title = parsed.get("title_original", ctx.title)
    ctx.localized_title = parsed.get(
        "title_localized", parsed.get("localized_title", "")
    )
    ctx.author = parsed.get("author", ctx.author)
    ctx.source_lang = parsed.get("source_lang", ctx.source_lang)
    ctx.category = parsed.get("category", ctx.category)
    ctx.book_summary = parsed.get("summary", "")
    ctx.style_notes = parsed.get("style_notes", "")
    for term in parsed.get("glossary_suggestions", []):
        if term.get("source") and term.get("target"):
            ctx.glossary_terms.append(term)

    # Re-search nếu cần
    if force_search or (parsed.get("needs_more_search") and parsed.get("search_query")):
        query = parsed.get("search_query") or user_feedback or ctx.title or preview[:120]
        logger.info("[Research] Re-searching: %s", query)
        try:
            results = await search_duckduckgo(query, max_results=5)
            ctx.search_results.extend(results)

            user2 = f"[Additional Results for: {query}]\n"
            for r in results[:3]:
                user2 += f"- {r.get('title', '')}: {r.get('content', '')[:300]}\n"
            user2 += "\nUpdate metadata based on these results. Return JSON."
            messages2 = [
                {
                    "role": "system",
                    "content": "Update book metadata based on search results. Return JSON.",
                },
                {"role": "user", "content": user2},
            ]
            raw2 = await _call_llm(
                messages2, ctx, response_format={"type": "json_object"}, temperature=0.2
            )
            try:
                p2 = json.loads(raw2)
                ctx.title = p2.get("title_original", ctx.title)
                ctx.author = p2.get("author", ctx.author)
                for term in p2.get("glossary_suggestions", []):
                    if term.get("source") and term.get("target"):
                        ctx.glossary_terms.append(term)
            except json.JSONDecodeError as e:
                logger.warning(
                    "[Research] Re-search non-JSON response: %s — %s", raw2[:100], e
                )
        except httpx.HTTPError as e:
            logger.warning("[Research] Re-search HTTP failed: %s", e)
        except (ConnectionError, TimeoutError) as e:
            logger.warning("[Research] Re-search connection failed: %s", e)

    logger.info(
        "[Research] Done: %s | %s | %d terms",
        ctx.title,
        ctx.author,
        len(ctx.glossary_terms),
    )
    return ctx


# ─── Agent 2: Translate Agent (with Deterministic Validation) ────────────


# System prompt được lấy động từ prompts.py theo category
def _get_translate_system(ctx: AgentContext) -> str:
    from ebook_translator.models import BookCategory
    from ebook_translator.translator.prompts import get_system_prompt

    try:
        cat = BookCategory(ctx.category)
    except ValueError:
        cat = BookCategory.GENERAL
    prompt = get_system_prompt(cat, ctx.source_lang, ctx.target_lang)
    # Thêm glossary rule
    prompt += "\n\nQUAN TRỌNG: Phải DÙNG CHÍNH XÁC các thuật ngữ trong Glossary. "
    prompt += "Viết HOA chữ cái đầu cho tên riêng, chiêu thức, vật phẩm."
    return prompt


async def translate_agent_with_validation(
    chunk: Chunk,
    glossary: list[GlossaryEntry],
    ctx: AgentContext,
    db: Database,
) -> str:
    """Translate Agent + Deterministic Validation + Retry nếu thiếu glossary terms.

    Flow: Cache check → Translate → Validate → Retry (nếu missing terms) → Lưu cache.
    """
    # 1. User-approved translation memory outranks model cache.
    remembered = await db.get_translation_memory(
        chunk.content_hash,
        ctx.source_lang,
        ctx.target_lang,
    )
    if remembered is not None:
        record_translation_memory_hit()
        logger.info("[Translate] Translation Memory HIT %s", chunk.content_hash[:12])
        return remembered

    # Build bounded long-form context from neighboring canonical chunks.
    neighborhood = await ContextBuilder(db).build_for_chunk(chunk)
    context = (
        f"[Book Info]\nTitle: {ctx.title}\nAuthor: {ctx.author}\n"
        f"Category: {ctx.category}\n"
        f"{ctx.source_lang} -> {ctx.target_lang}\n"
    )
    if ctx.book_summary:
        context += f"Summary: {ctx.book_summary}\n"
    if ctx.style_notes:
        context += f"Style: {ctx.style_notes}\n"
    rendered_neighborhood = neighborhood.render()
    if rendered_neighborhood:
        context += f"\n{rendered_neighborhood}\n"

    # Glossary terms
    all_terms: list[dict] = []
    if glossary:
        context += "\n[Glossary - MANDATORY]\n"
        for g in glossary:
            context += f"- {g.source_term} -> {g.target_term}\n"
            all_terms.append({"source": g.source_term, "target": g.target_term})
    for g in ctx.glossary_terms:
        context += f"- {g['source']} -> {g['target']}\n"
        all_terms.append(g)

    context += f"\n[Text]\n{chunk.original_text}"

    messages = [
        {"role": "system", "content": _get_translate_system(ctx)},
        {"role": "user", "content": context},
    ]

    context_hash = prompt_fingerprint(messages)
    cached = await db.get_cached(
        content_hash=chunk.content_hash,
        source=ctx.source_lang,
        target=ctx.target_lang,
        model=ctx.model,
        context_hash=context_hash,
    )
    if cached is not None:
        record_cache_hit()
        logger.info("[Translate] Cache HIT %s", chunk.content_hash[:12])
        return cached

    # 2. Translate
    result = await _call_llm(messages, ctx, temperature=0.3)

    # 2.5 AutoFormat (trước validate để loại bỏ lỗi chính tả ảnh hưởng đến matching)
    from ebook_translator.utils.autoformat import autoformat_chunk

    result = autoformat_chunk(chunk.original_text, result)

    # 3. Deterministic Validation — chỉ check terms CÓ trong source text
    missing: list[str] = []
    for attempt in range(MAX_RETRIES):
        missing = check_glossary_terms(chunk.original_text, result, all_terms)
        if not missing:
            break

        logger.warning(
            "[Validate] Missing terms (attempt %d/%d): %s",
            attempt + 1,
            MAX_RETRIES,
            missing,
        )
        retry_prompt = build_retry_prompt(chunk.original_text, result, missing)
        messages = [
            {
                "role": "system",
                "content": _get_translate_system(ctx)
                + "\nIMPORTANT: The previous attempt MISSED glossary terms. Include them this time.",
            },
            {"role": "user", "content": retry_prompt},
        ]
        result = await _call_llm(messages, ctx, temperature=0.3)

    if missing:
        logger.warning(
            "[Validate] Still missing after %d retries (continuing): %s",
            MAX_RETRIES,
            missing,
        )

    # 4. Save cache
    cache_entry = CacheEntry(
        content_hash=chunk.content_hash,
        context_hash=context_hash,
        source_lang=ctx.source_lang,
        target_lang=ctx.target_lang,
        model=ctx.model,
        translated_text=result,
    )
    await db.set_cached(cache_entry)

    return result
