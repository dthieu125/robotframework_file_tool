# Robot Framework File Tool

Tài liệu này mô tả nhanh cách dùng dự án bằng tiếng Việt. README chính của repository là tiếng Anh.

## Mục tiêu

Dự án cung cấp một ứng dụng web Flask và một công cụ dòng lệnh để làm việc với Robot Framework:

- Phân tích file `.robot` / `.resource`.
- Chạy test Robot Framework từ giao diện web.
- Gộp nhiều file `output.xml` thành một bộ `output.xml`, `log.html`, `report.html`.
- Định dạng lại tên test case hàng loạt.

## Chạy ứng dụng web

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Hoặc trên Windows có thể chạy:

```bash
start.bat
```

Mặc định ứng dụng chạy ở `http://localhost:5000`.

## Report Merger

Tab Report Merger cho phép upload ít nhất hai file `output.xml`.

Các chế độ gộp:

- Combine: gộp các test từ nhiều file vào cùng báo cáo.
- Update / Replace: file phía sau thay thế test cùng tên ở file phía trước. Cách dùng phổ biến là upload result cũ trước, rerun result mới sau.

Nếu để trống Output name, tool sẽ tạo đúng tên mặc định của Robot Framework:

- `output.xml`
- `log.html`
- `report.html`

Nếu nhập Output name, ví dụ `sprint42`, tool sẽ tạo:

- `sprint42_output.xml`
- `sprint42_log.html`
- `sprint42_report.html`

## Setting của Report Merger

Nút Setting trong tab Report Merger hiện hỗ trợ:

- Giữ lịch sử kết quả cũ bên cạnh kết quả mới nhất.
- Chỉ giữ trạng thái mới nhất, xoá các block old result history do `rebot --merge` tạo ra.
- Tự clear danh sách input files sau khi merge thành công.
- Cấu hình thời gian tự xoá file upload/result cũ.
- Clean old files thủ công ngay từ UI.

Lưu ý: khi chọn chỉ giữ latest status, tool xoá phần text history trong thẻ `<test><status>` trước khi sinh `log.html` và `report.html`.

## CLI `rf_merge.py`

CLI dùng khi không cần giao diện web.

```bash
python rf_merge.py old.xml rerun.xml
python rf_merge.py --update old.xml rerun.xml
python rf_merge.py --update --latest-only old.xml rerun.xml
python rf_merge.py -o reports -n sprint42 --update old.xml rerun.xml
```

Các option quan trọng:

- `-o` / `--output-dir`: thư mục output.
- `-n` / `--name`: prefix file output. Để trống sẽ sinh `output.xml`, `log.html`, `report.html`.
- `--update`: thay thế test cùng tên bằng kết quả từ file phía sau.
- `--latest-only`: dùng cùng `--update` để chỉ giữ trạng thái mới nhất.
- `--flatten`: đưa test case về cùng một cấp suite.
- `--xml-only`: chỉ tạo XML, không tạo HTML.
- `--no-dedup`: tắt tự loại file trùng nội dung.

## File runtime và git

Các thư mục runtime không đưa lên git:

- `uploads/`
- `results/`
- `__pycache__/`
- `technical_docs/`

`technical_docs/` hiện là tài liệu local, đang bị ignore theo yêu cầu loại khỏi repository.
