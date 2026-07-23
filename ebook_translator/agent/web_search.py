"""Web Search Agent — tìm metadata sách qua DuckDuckGo (free) + AI knowledge.

AI có kiến thức nền về hàng triệu cuốn sách nổi tiếng (VD: God Father = Bố Già).
Nếu không nhận ra, fallback tìm kiếm DuckDuckGo free (không cần API key).

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

MAX_PREVIEW_CHARS = 2000


@dataclass
class MetadataResult:
    """Kết quả từ Web Search Agent."""
    title: str = ""
    author: str = ""
    source_lang: str = "en"
    target_lang: str = "vi"
    localized_title: str = ""
    category: str = "general"
    description: str = ""
    confidence: float = 0.0
    sources: list[str] = field(default_factory=list)
    from_knowledge: bool = False  # True = AI tự biết, False = cần search


async def search_duckduckgo(query: str, max_results: int = 3) -> list[dict]:
    """Search DuckDuckGo (free, không cần API key)."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for _, r in enumerate(ddgs.text(query, max_results=max_results)):
                results.append({
                    "title": r.get("title", ""),
                    "content": r.get("body", ""),
                    "url": r.get("href", ""),
                })
                if len(results) >= max_results:
                    break
        return results
    except ImportError:
        logger.warning("duckduckgo_search not installed, skipping web search")
        return []
    except Exception as e:
        logger.warning("DuckDuckGo search failed: %s", e)
        return []


SYSTEM_PROMPT = """You are a book metadata specialist. You have been trained on millions of books.
First, use YOUR EXISTING KNOWLEDGE to identify the book. Many famous books are in your training data.
Only use web search results as supplementary information.

Return ONLY valid JSON with these fields:
{
  "title": "Original book title in the source language",
  "author": "Author name in Vietnamese (if Chinese/Vietnamese name, keep original order; if English name, suggest Vietnamese transliteration)",
  "source_lang": "Language code (en/zh/ja/ko/fr/de/es...)",
  "target_lang": "Target language code (default: vi for Vietnamese)",
  "localized_title": "TRANSLATED book title in Vietnamese — this MUST be a different, Vietnamese translation of the title, NOT the original title",
  "category": "van_hoc | lich_su | hien_dai | tien_hiep | general",
  "description": "Brief description in Vietnamese (max 100 chars)",
  "confidence": 0.0-1.0,
  "from_knowledge": true or false (true = you recognized this book from your training data)
}

Examples:
Excerpt: "I am the God Father" -> title: "The Godfather", localized_title: "Bố Già", author: "Mario Puzo", from_knowledge: true
Excerpt: "三体" -> title: "三体", localized_title: "Tam Thể", author: "Lưu Từ Hân", from_knowledge: true
Excerpt: "Harry Potter and the Sorcerer's Stone" -> title: "Harry Potter and the Sorcerer's Stone", localized_title: "Harry Potter và Hòn đá Phù thủy", author: "J.K. Rowling", from_knowledge: true
"""


async def extract_metadata(
    preview: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    base_url: str = "https://api.openai.com/v1",
    user_feedback: str = "",
    force_search: bool = False,
) -> MetadataResult:
    """Extract book metadata — AI knowledge first, DuckDuckGo fallback.

    Args:
        preview: Text đầu sách để phân tích.
        api_key: API key.
        model: Model name.
        base_url: API base URL.
        user_feedback: Thông tin bổ sung từ người dùng.
        force_search: Nếu True, luôn search web kể cả AI có biết hay không.
    """
    # Bước 1: Gọi LLM với kiến thức nền trước
    preview_trunc = preview[:MAX_PREVIEW_CHARS]
    user = f"[Text Excerpt]\n{preview_trunc}\n"

    if user_feedback:
        user += f"\n[User Feedback]\n{user_feedback}\n"

    user += "\nUse your existing knowledge first. Return the JSON now."

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content_text = data["choices"][0]["message"]["content"]

    try:
        parsed = json.loads(content_text)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON: %s", content_text[:200])
        return MetadataResult()

    from_knowledge = parsed.get("from_knowledge", False)
    confidence = parsed.get("confidence", 0.0)

    # Nếu AI không tự tin hoặc không biết -> search DuckDuckGo
    search_results: list[dict] | None = None
    if force_search or (not from_knowledge) or confidence < 0.5:
        query_lines = [line.strip() for line in preview.strip().split("\n") if line.strip()][:2]
        query = " ".join(query_lines)[:150]
        search_query = f'"{query}" book novel author'
        logger.info("Searching DuckDuckGo for: %s", search_query)
        search_results = await search_duckduckgo(search_query)
        logger.info("Got %d search results", len(search_results))

        if search_results:
            # Gọi LLM lần 2 với web results
            user2 = f"[Text Excerpt]\n{preview_trunc}\n\n[Web Search Results]\n"
            for i, r in enumerate(search_results[:3], 1):
                title = r.get("title", "")
                content = r.get("content", "")[:500]
                url = r.get("url", "")
                user2 += f"\n--- Result {i} ---\nTitle: {title}\nContent: {content}\nURL: {url}\n"
            if user_feedback:
                user2 += f"\n[User Feedback]\n{user_feedback}\n"
            user2 += "\nNow with web search results, return the JSON."

            messages2 = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user2},
            ]
            async with httpx.AsyncClient(timeout=30) as client:
                resp2 = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages2,
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                    },
                )
                resp2.raise_for_status()
                data2 = resp2.json()
                content_text = data2["choices"][0]["message"]["content"]
                try:
                    parsed = json.loads(content_text)
                except json.JSONDecodeError:
                    pass  # giữ kết quả cũ

    sources = [r.get("url", "") for r in search_results] if search_results else []
    return MetadataResult(
        title=parsed.get("title", ""),
        author=parsed.get("author", ""),
        source_lang=parsed.get("source_lang", "en"),
        target_lang=parsed.get("target_lang", "vi"),
        localized_title=parsed.get("localized_title", ""),
        category=parsed.get("category", "general"),
        description=parsed.get("description", ""),
        confidence=parsed.get("confidence", 0.0),
        sources=sources,
        from_knowledge=from_knowledge,
    )


async def get_preview_text(file_path: str, max_chars: int = 3000) -> str:
    """Lấy đoạn text đầu sách để phân tích."""
    from ebook_translator.parsers.epub_parser import EpubParser
    from ebook_translator.parsers.txt_parser import TxtParser

    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    if ext == "epub":
        parser = EpubParser()
    elif ext == "txt":
        parser = TxtParser()
    else:
        return ""

    parsed = parser.parse(file_path)
    preview = ""
    for chapter in parsed.chapters:
        for para in chapter:
            preview += para + "\n"
            if len(preview) >= max_chars:
                break
        if len(preview) >= max_chars:
            break

    return preview[:max_chars]
