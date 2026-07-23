# Kế hoạch Triển khai: Ebook Translator (Audit v2 — Ngon-Bổ-Rẻ)

## Mục tiêu

Xây dựng công cụ dịch E-book tự động, bản địa hóa, cá nhân hóa văn phong, đồng nhất thuật ngữ.
**Nguyên tắc:** Lõi trước — bề nổi sau. Cache từ Ngày 1. Error recovery bắt buộc.

---

## Phase 1 (MVP — 2 Tuần): Translation Core

**Trọng tâm:** Parse → Chunk → Dịch → Ghép → Xuất. Prompt chay, chưa cần UI.

| Module | Công nghệ | Chi tiết |
|---|---|---|
| **Parser** | `ebooklib` + `BeautifulSoup` (.epub) | Extract sách → list paragraph. DRM → báo lỗi |
| **Parser** | `chardet` + `io` (.txt) | Auto-detect encoding, heuristic chapter split (dòng trống, số chương) |
| **Database** | SQLite + `WAL` + `aiosqlite` | 3 bảng: `Books` (metadata), `Chunks` (paragraph gốc + dịch), `Glossary` (từ điển theo đầu sách) |
| **Cache** | Fingerprinting bằng `hashlib.sha256` | Hash nội dung paragraph → cache translation. Lần chạy sau check hash trước khi gọi API |
| **AI Call** | `httpx.AsyncClient` + `tenacity` | retry 3 lần exponential backoff. Ghi log lỗi + resume từ chunk cuối |
| **Chunking** | Paragraph-level | 1 paragraph = 1 chunk. Nếu paragraph > 4000 token → split tiếp bằng câu |
| **Export** | `ebooklib` (re-build .epub) | Ghép chunk đã dịch → .epub hoàn chỉnh, giữ nguyên CSS gốc |

**Output:** CLI tool chạy được: `python translate.py input.epub` → ra `input_vn.epub`.

---

## Phase 2 (1 Tuần): Tauri UI + Prompt Routing

**Trọng tâm:** Có giao diện, có phân luồng văn phong, có thanh tiến độ.

| Module | Công nghệ | Chi tiết |
|---|---|---|
| **Frontend** | Tauri 2.x + React (TypeScript) | Desktop app, nhẹ (~5MB), cross-platform |
| **Backend** | Python sidecar (Tauri gọi qua stdio) | Giữ nguyên core Python ở Phase 1 |
| **Progress** | Server-Sent Events (SSE) | Push trạng thái chunk → UI realtime |
| **Prompt Routing** | Router theo `category` | Văn học / Lịch sử / Hiện đại / Tiên hiệp → system prompt riêng |
| **Glossary UI** | Table edit trong Tauri | Anh thêm/sửa/xoá từ điển tay, persist vào SQLite |
| **Manual override** | Ô nhập API key + model selector | Chọn model, temperature, top_p |

**Output:** App desktop: kéo thả file → chọn thể loại → bấm Dịch → thấy progress → xuất file.

---

## Phase 3 (Tùy chọn 1): Web Search Agent + HITL

**Trọng tâm:** AI tự tìm metadata + anh duyệt.

- **Web Search Agent** — Tra tên gốc, tác giả, đề xuất tên bản địa hóa
- **HITL Screen** — Anh confirm/sửa metadata trước khi lưu vào DB
- **Không động vào pipeline dịch** — HITL chỉ cho metadata, không cho chunk translation

---

## Phase 4 (Tùy chọn 2): Cover Generator

**Trọng tâm:** Sinh ảnh bìa tự động.

- **Stable Diffusion (local)** — diffusers, không cần API key
- **Text overlay** — Pillow: Tên sách + Tác giả + Dịch giả
- **Đóng dấu bản quyền** — watermark mờ

---

## 🔥 Kỹ thuật xương sống (xuyên suốt)

| Kỹ thuật | Mô tả | Áp dụng từ |
|---|---|---|
| **Fingerprinting (Cache)** | `sha256(paragraph_text + source_lang + target_lang)` → tra cache trước khi gọi API. Cache lưu SQLite. Chống tốn tiền dịch lại | Phase 1 |
| **Exponential Backoff** | retry lỗi 429/5xx: 1s → 4s → 16s. Nếu 3 lần đều fail → ghi log + skip chunk, không crash | Phase 1 |
| **Resume** | Chạy lại tool → check DB: chunk nào có translation rồi → skip. Chỉ dịch chunk `status=pending` | Phase 1 |
| **Token Budget** | Track token usage mỗi chunk. Nếu sắp hết budget → pause, hỏi anh | Phase 2 |
