"""Web Search Agent — tìm metadata sách qua Tavily API hoặc LLM-only.

Wing: tcdserver | Topic: ebook_translator | Updated: 2026-07-22 14:00
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

MAX_PREVIEW_CHARS = 2000  # Số ký tự đầu sách gửi cho LLM


@dataclass
class MetadataResult:
    """Kết quả từ Web Search Agent."""
    title: str = ""
    author: str = ""
    source_lang: str = "en"
    localized_title: str = ""
    category: str = "general"
    description: str = ""
    confidence: float = 0.0  # 0.0 - 1.0
    sources: list[str] = field(default_factory=list)


async def search_tavily(query: str, api_key: str, max_results: int = 3) -> list[dict]:
    """Gọi Tavily Search API."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": max_results, "include_answer": True},
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        # Gắn answer vào đầu
        if data.get("answer"):
            results.insert(0, {"title": "AI Summary", "content": data["answer"], "url": ""})
        return results


def _build_search_query(preview: str) -> str:
    """Tạo search query từ đoạn đầu sách."""
    lines = preview.strip().split("\n")
    # Lấy 2 dòng đầu làm query
    query_lines = [line.strip() for line in lines if line.strip()][:2]
    query = " ".join(query_lines)
    if len(query) > 150:
        query = query[:150]
    return f'"{query}" book author'


def _build_llm_prompt(
    preview: str,
    search_results: list[dict] | None = None,
) -> list[dict]:
    """Build messages cho LLM để extract metadata."""
    system = """You are a book metadata specialist. Analyze the text excerpt and search results below.
Return ONLY valid JSON with these fields:
{
  "title": "Original book title",
  "author": "Author name (or empty string if unknown)",
  "source_lang": "Language code (en/zh/ja/ko/fr/de/es...)",
  "localized_title": "Suggested Vietnamese title translation",
  "category": "van_hoc | lich_su | hien_dai | tien_hiep | general",
  "description": "Brief description in Vietnamese (max 100 chars)",
  "confidence": 0.0-1.0
}"""

    preview_trunc = preview[:MAX_PREVIEW_CHARS]
    user = f"[Text Excerpt]\n{preview_trunc}\n"

    if search_results:
        user += "\n[Web Search Results]\n"
        for i, r in enumerate(search_results[:3], 1):
            title = r.get("title", "")
            content = r.get("content", "")[:500]
            url = r.get("url", "")
            user += f"\n--- Result {i} ---\nTitle: {title}\nContent: {content}\nURL: {url}\n"

    user += "\nReturn the JSON now."

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def extract_metadata(
    preview: str,
    api_key: str,
    model: str = "gpt-4o-mini",
    base_url: str = "https://api.openai.com/v1",
) -> MetadataResult:
    """Extract book metadata — với web search nếu có Tavily key, nếu không thì LLM-only.

    Args:
        preview: Đoạn text đầu sách (vài chapter đầu).
        api_key: OpenAI API key.
        model: Model name.
        base_url: API base URL.

    Returns:
        MetadataResult với thông tin tìm được.
    """
    search_results: list[dict] | None = None

    # Bước 1: Web search (nếu có Tavily key)
    if TAVILY_API_KEY:
        try:
            query = _build_search_query(preview)
            logger.info("Searching Tavily for: %s", query)
            search_results = await search_tavily(query, TAVILY_API_KEY)
            logger.info("Got %d search results", len(search_results))
        except Exception as e:
            logger.warning("Tavily search failed (non-fatal): %s", e)

    # Bước 2: LLM extraction
    messages = _build_llm_prompt(preview, search_results)
    messages.append({"role": "user", "content": "Return the JSON now."})

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
        content = data["choices"][0]["message"]["content"]

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON: %s", content[:200])
        return MetadataResult()

    sources = [r.get("url", "") for r in search_results] if search_results else []
    return MetadataResult(
        title=parsed.get("title", ""),
        author=parsed.get("author", ""),
        source_lang=parsed.get("source_lang", "en"),
        localized_title=parsed.get("localized_title", ""),
        category=parsed.get("category", "general"),
        description=parsed.get("description", ""),
        confidence=parsed.get("confidence", 0.0),
        sources=sources,
    )


async def get_preview_text(file_path: str, max_chars: int = 3000) -> str:
    """Lấy đoạn text đầu sách để phân tích."""
    from ebook_translator.parsers.epub_parser import EpubParser
    from ebook_translator.parsers.txt_parser import TxtParser

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".epub":
        parser = EpubParser()
    elif ext == ".txt":
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
