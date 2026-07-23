\# Kế hoạch Triển khai: Ebook Translator (Chuẩn Công Nghiệp)



\## Mục tiêu

Xây dựng công cụ dịch thuật E-book tự động có khả năng bản địa hóa, cá nhân hóa văn phong và đảm bảo đồng nhất thuật ngữ tuyệt đối.



\### Phase 1: Core Foundation \& Book Management

\* \*\*Database Setup:\*\* Cấu hình SQLite với chế độ `WAL` (Write-Ahead Logging) và dùng `aiosqlite` để xử lý truy vấn bất đồng bộ.

\* \*\*UI/UX Cơ bản:\*\* Xây dựng Tab Quản lý sách (Danh sách sách, trạng thái dịch).

\* \*\*Asset Management:\*\* Tích hợp module xử lý ảnh bìa (Upload thủ công hoặc gọi API tạo ảnh, tự động in đè text Tên sách, Tác giả, Dịch giả bằng thư viện Pillow).



\### Phase 2: Agentic Web Search \& Human-in-the-Loop (HITL)

\* \*\*Web Search Skill:\*\* AI tự động tìm kiếm tên gốc, tác giả, thể loại và đề xuất tên bản địa hóa (VD: \*House of Cards\* -> \*Ván bài chính trị\*).

\* \*\*HITL Checkpoint:\*\* Xây dựng UI Bước 1 để người dùng (Anh) xác nhận/sửa đổi Metadata (Tên sách, tác giả - VD: sửa \*Lưu Cừu Hân\* thành \*Lưu Từ Hân\*) trước khi lưu vào Database.



\### Phase 3: AI Translation Pipeline (Trái tim hệ thống)

\* \*\*Dynamic RAG \& Fingerprinting:\*\* Băm (Hash) các thuật ngữ/danh từ riêng. Bơm từ điển vào System Prompt để đảm bảo nhất quán 100%.

\* \*\*Prompt Routing:\*\* Xây dựng bộ định tuyến Prompt theo thể loại (Văn học, Lịch sử/Quân sự, Hiện đại, Tiên hiệp) đã chốt ở Phase 2 để điều chỉnh văn phong.

\* \*\*Async Workers:\*\* Dịch bất đồng bộ hàng loạt chương sách mà không gây nghẽn Database (nhờ SQLite WAL).



\### Phase 4: E-book Export

\* \*\*Đóng gói:\*\* Gom các Chunks đã dịch thành file `.epub` hoàn chỉnh (kèm ảnh bìa).

