# Tài Liệu Kỹ Thuật

Tài liệu này dành cho người maintain dự án Robot Framework File Tool.

## Tổng quan kiến trúc

Ứng dụng gồm hai phần chính:

- `app.py`: Flask app, định nghĩa route HTTP, upload/download, cleanup, settings.
- `modules/`: chứa logic nghiệp vụ cho web app.
- `rf_merge.py`: CLI độc lập, có logic merge riêng để có thể copy và chạy không cần Flask.
- `templates/index.html` và `static/js/main.js`: giao diện web một trang.

## Report Merger trong web app

Route chính:

- `POST /api/merge`
- `GET /api/merge/<run_id>/report`
- `GET /api/merge/<run_id>/log`
- `GET /api/download/<run_id>`

Các form field quan trọng của `/api/merge`:

- `files`: danh sách file `output.xml`.
- `flatten`: `true` hoặc `false`.
- `update_mode`: `true` hoặc `false`.
- `output_name`: prefix output. Nếu rỗng thì dùng `output.xml`, `log.html`, `report.html`.
- `suite_name`: tên suite root, optional.
- `keep_update_history`: `true` để giữ history cũ, `false` để chỉ giữ latest status.

## Cách đặt tên output

Helper `_output_paths(output_dir, output_name)` trong `modules/merger.py` quyết định tên file output.

Nếu `output_name` có giá trị:

- `<output_name>_output.xml`
- `<output_name>_log.html`
- `<output_name>_report.html`

Nếu `output_name` rỗng hoặc `None`:

- `output.xml`
- `log.html`
- `report.html`

Route xem report/log đã được cập nhật để tìm cả tên mặc định và tên dạng prefix.

## Update / Replace và latest-only

Robot Framework `rebot --merge` mặc định giữ lịch sử kết quả cũ trong text của thẻ:

```xml
<test>
  <status>... old result history ...</status>
</test>
```

Khi merge nhiều lần, ví dụ FAIL -> FAIL -> PASS, phần old history có thể lặp nhiều block FAIL trong `output.xml`, `log.html`, `report.html`.

Để xử lý, web app và CLI có helper:

- `modules/merger.py`: `_strip_merge_history_messages(output_xml)`
- `rf_merge.py`: `_strip_merge_history_messages(output_xml)`

Helper này tìm các `<test><status>` có marker:

- `Test has been re-executed and results merged`
- hoặc `class="merge"`

Sau đó xoá text của status, giữ nguyên attribute `status`, `start`, `elapsed`.

Luồng update mode hiện tại:

1. Chạy `python -m robot.rebot --merge` để tạo XML đã merge.
2. Nếu không giữ history, xoá merge history trong XML.
3. Dùng `ExecutionResult` để repair suite timing.
4. Save lại XML.
5. Chạy `robot.rebot` lần hai để sinh `log.html` và `report.html`.

## Settings và cleanup

File setting local:

- `settings.json`

File này bị ignore bởi git.

Setting hiện có:

- `cleanup_age_hours`: số giờ giữ file upload/result trước khi tự xoá.

Route settings:

- `GET /api/settings`: đọc setting.
- `POST /api/settings`: lưu setting.
- `POST /api/cleanup`: xoá ngay file cũ hơn số giờ truyền vào.

Worker cleanup:

- `_start_cleanup_worker()` chạy khi start app trực tiếp bằng `python app.py`.
- Worker kiểm tra mỗi 1 giờ.
- Xoá item cũ trong `uploads/` và `results/`.

## Frontend settings

Các setting của Report Merger được xử lý trong IIFE Report Merger của `static/js/main.js`.

State local:

- `MERGER_SETTINGS_KEY = 'rf-merger-settings'`
- `updateHistory`: `keep` hoặc `latest`
- `clearInputsAfterMerge`: boolean
- `cleanupAgeHours`: number

Khi bấm Merge:

- JS append `keep_update_history` vào `FormData`.
- Nếu setting clear input được bật, sau merge thành công JS gọi `clearMergerInputs()`.

## CLI `rf_merge.py`

CLI đã đồng bộ logic quan trọng với `modules/merger.py`.

Các option mới hoặc đáng chú ý:

- `-n` / `--name`: prefix output. Mặc định rỗng để tạo `output.xml`, `log.html`, `report.html`.
- `--update`: dùng `rebot --merge`.
- `--latest-only`: xoá old result history trong update mode.

Ví dụ:

```bash
python rf_merge.py --update --latest-only old.xml rerun.xml
python rf_merge.py --update -n sprint42 old.xml rerun.xml
python rf_merge.py --xml-only old.xml rerun.xml
```

`merge_xml_reports()` của CLI trả về tuple:

```python
(created_files, stripped_history_count)
```

`stripped_history_count` là số test đã bị xoá merge history.

## Lưu ý đồng bộ code

Hiện có logic trùng giữa:

- `modules/merger.py`
- `rf_merge.py`

Lý do: CLI cần độc lập, không phụ thuộc Flask app. Khi sửa logic merge, nên cập nhật cả hai file.

Các helper cần chú ý đồng bộ:

- `_suite_elapsed_ms`
- `_repair_suite_timing`
- `_output_paths`
- `_strip_merge_history_messages`
- logic update mode
- logic combine mode

## Kiểm tra thủ công sau khi sửa merge

Nên chạy các bước sau:

1. Tạo hai file Robot cùng tên test, file cũ FAIL, file mới PASS.
2. Chạy web merge update mode, bật keep history.
3. Chạy web merge update mode, chọn latest-only.
4. Kiểm tra XML latest-only không còn marker `old-status` hoặc `class="merge"`.
5. Chạy CLI:

```bash
python rf_merge.py --update --latest-only old/output.xml new/output.xml
python rf_merge.py --update -n sprint42 old/output.xml new/output.xml
```

## Kiểm tra tự động

Kiểm tra cú pháp:

```bash
python -m compileall app.py modules rf_merge.py
node --check static/js/main.js
```

Chạy test nếu đã cài pytest:

```bash
pytest tests/ -q
```

## Ghi chú về repository

`technical_docs/` đang bị `.gitignore` loại khỏi git. Tài liệu này dùng để ghi chú local và không được push lên repository nếu không thay đổi rule ignore.
