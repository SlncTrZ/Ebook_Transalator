\# Kiến trúc Hệ thống: Ebook Translator



\## Sơ đồ Khối (Component Diagram)



1\.  \*\*UI/UX Layer:\*\*

&#x20;   \*   \*\*Book Manager Tab:\*\* Quản lý thư viện, thêm mới sách, gán ảnh bìa.

&#x20;   \*   \*\*HITL Verification Screen:\*\* Màn hình chốt chặn để duyệt Metadata từ AI Search.

2\.  \*\*Agentic Layer:\*\*

&#x20;   \*   \*\*Web Search Agent:\*\* Đi thu thập thông tin sách và tìm tên bản địa hóa chuẩn.

&#x20;   \*   \*\*Cover AI Generator:\*\* Gọi API sinh ảnh bìa và xử lý text overlay.

3\.  \*\*Data Layer (SQLite - Embedded Database):\*\*

&#x20;   \*   Kích hoạt: `PRAGMA journal\_mode=WAL;` (Chống lock DB).

&#x20;   \*   Bảng: `Books` (Metadata), `Chunks` (Đoạn text), `Glossary` (Từ điển theo truyện).

4\.  \*\*AI Pipeline (Translation Engine):\*\*

&#x20;   \*   \*\*Prompt Router:\*\* Bẻ nhánh Prompt dựa trên trường `Category` (Văn học, Lịch sử, Tiên hiệp...).

&#x20;   \*   \*\*Glossary Injector:\*\* Dùng \*\*Fingerprinting\*\* so khớp chunk text hiện tại với `Glossary`, ép AI dùng đúng từ.

&#x20;   \*   \*\*Async Translation Pool:\*\* Luồng worker xử lý dịch bất đồng bộ qua API (OpenAI/Anthropic).



\---



\## Bảng thiết kế Kỹ thuật cốt lõi



| Module | Công nghệ / Thuật ngữ | Chức năng \& Tối ưu |

|---|---|---|

| \*\*Database\*\* | SQLite + `WAL` + `aiosqlite` | Triệt tiêu lỗi "Database is locked", giảm \*\*Latency\*\* khi luồng AI ghi dữ liệu liên tục. |

| \*\*Xác thực Đầu vào\*\* | \*\*Human-in-the-Loop (HITL)\*\* | Cho phép người dùng duyệt và sửa Metadata (Tác giả, Tên sách) trước khi dịch. |

| \*\*Định hướng Văn phong\*\* | \*\*Prompt Routing\*\* | Tự động chuyển đổi System Prompt (hoa mỹ, súc tích, đời thường) theo từng thể loại sách. |

| \*\*Tính Nhất quán\*\* | \*\*RAG \& Fingerprinting\*\* | Băm dữ liệu để truy xuất từ điển siêu tốc, ép AI dịch chuẩn tên nhân vật, pháp bảo, chiêu thức. |

| \*\*Tạo Ảnh Bìa\*\* | API (Midjourney/DALL-E) + Pillow | Tự động hóa tạo ảnh và đóng dấu bản quyền Dịch giả mà không cần Photoshop. |

