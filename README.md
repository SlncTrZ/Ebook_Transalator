# Ebook Translator

Công cụ dịch thuật E-book tự động với khả năng bản địa hóa, cá nhân hóa văn phong và đảm bảo đồng nhất thuật ngữ.

## Tính năng chính

- **Quản lý thư viện sách** — Thêm sách, gán ảnh bìa, theo dõi trạng thái dịch
- **Human-in-the-Loop (HITL)** — Duyệt Metadata từ AI trước khi dịch
- **AI Translation Pipeline** — Dịch bất đồng bộ qua OpenAI/Anthropic với Prompt Routing theo thể loại
- **RAG & Fingerprinting** — Đảm bảo thuật ngữ nhất quán 100% nhờ từ điển nhúng
- **Tạo ảnh bìa tự động** — Midjourney/DALL-E + Pillow overlay
- **Xuất .epub** — Đóng gói sách hoàn chỉnh

## Kiến trúc

```
UI/UX Layer        → Book Manager, HITL Screen
Agentic Layer      → Web Search Agent, Cover Generator
AI Pipeline        → Prompt Router → Glossary Injector → Async Translation Pool
Data Layer         → SQLite (WAL mode) — Books, Chunks, Glossary
```

## Công nghệ

- **Backend:** Python (aiosqlite, Pillow)
- **Database:** SQLite + WAL mode
- **AI:** OpenAI / Anthropic API
- **UI:** (TBD)
- **Container:** Docker Compose

## Phát triển

```bash
# Clone & setup
git clone https://github.com/SlncTrZ/Ebook_Transalator.git
cd Ebook_Transalator
python -m venv .venv
source .venv/bin/activate  # hoặc .venv\Scripts\activate trên Windows
pip install -r requirements.txt
```

---

*Dự án bởi **Trương Công Định (SlncTrZ)** — dành cho cộng đồng dịch thuật E-book.*
