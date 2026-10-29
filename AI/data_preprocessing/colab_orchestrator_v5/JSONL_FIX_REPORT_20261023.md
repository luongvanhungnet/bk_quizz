# Sửa lỗi JSONL ở unit_0061 — 23/10/2026

## Nguyên nhân đã tái hiện

Log đầu vào xác minh 60/134 ZIP hoàn chỉnh, tương ứng 6.000 trang. Gói tiếp theo là IT4025, trang 264–363. Native extraction hoàn thành nhưng `corpus.package_job()` gọi bộ đọc `io_utils.jsonl()` dùng `str.splitlines()` và báo `Unterminated string starting at: line 1 column 841 (char 840)`.

PDF gốc có U+2028 ở chín trang trong khoảng này. Sau native extraction với `sort=True`, sáu trang vẫn giữ ký tự này. JSON cho phép ký tự U+2028 nằm trong một chuỗi; `json.dumps(..., ensure_ascii=False)` lưu nó nguyên trạng. `str.splitlines()` lại tách tại U+2028, U+2029 và U+0085, làm một bản ghi hợp lệ thành nhiều đoạn JSON hỏng. Đây là lỗi phân định dòng, không phải bằng chứng file bị ghi dở, thiếu RAM hoặc VLM sinh sai JSON.

Kiểm thử với đúng PDF gốc đã tái hiện **cùng thông báo và vị trí cột 841**, rồi xử lý thành công cùng 100 trang/304 record bằng bộ đọc mới. Xem `JSONL_IT4025_REGRESSION_20261023.json`.

## Thay đổi

- `jsonl_adapter.py` đọc ranh giới dòng LF thực, hỗ trợ CRLF/BOM và giữ nguyên dấu tiếng Việt, dấu toán học, U+0085/U+2028/U+2029 bên trong chuỗi. File không bị ghi lại.
- Cài adapter trước khi import các hàm core trong controller, subprocess native/merge, warm model worker, preflight và local importer. Các alias `from io_utils import jsonl` đã được import cũng được cập nhật trong bộ nhớ.
- `unit_store.py` kiểm nội dung JSONL trong ZIP bằng cùng bộ đọc, để ZIP hợp lệ không bị coi nhầm là chưa hoàn thành khi khởi động lại. Các công cụ audit/reuse local cũng được sửa.
- JSON thực sự bị cắt hoặc hỏng vẫn gây lỗi, kèm đường dẫn file/member, số dòng vật lý và cột. Không bỏ qua bản ghi hỏng, không đoán phần nội dung còn thiếu.
- Core v5.0.0 vẫn nguyên 48 file. Không sửa PDF, 134 input, manifest nguồn, ZIP kết quả, receipt hoặc SQLite kiểm duyệt. Semantic verification/human review/CPT gate không thay đổi.

## Tiếp tục ngay trong phiên Colab đang có

1. Sau khi cell lỗi đã dừng, mở `COLAB_JSONL_REPAIR_AND_RESUME.txt`, sao chép toàn bộ vào **một code cell mới** rồi chạy.
2. Cell đóng controller/model worker cũ, kiểm cú pháp và anchor, sao lưu runtime lên `BASE/runtime_hotfixes/jsonl_20261023_*`, rồi chỉ vá các điểm đọc JSONL. **Giữ nguyên `native_batches.py`**, kể cả sửa crop đang có trên Colab. Không cài lại venv, không xóa cache/input/kết quả.
3. Cell tự quét lại các ZIP đã lưu rồi chạy gói thiếu. Với tiến độ đúng như log, gói kế tiếp là `unit_0061`; 60 gói đã lưu sẽ được nhận lại nếu tiếp tục qua kiểm tra hash. Gói 61 được chạy lại từ đầu theo chính sách unit độc lập. Nếu Drive hiện đã có thêm kết quả hợp lệ, các gói đó cũng được bỏ qua.
4. `RETRY_FAILED=True` trong cell kết hợp thử lại các gói đã auto-skip, mỗi gói tối đa một lần/lượt cell. Gói 25 vẫn nằm trong `EXCLUDED_UNITS` theo cell trước; đổi thành `set()` khi muốn thử lại cả gói này. Lỗi mới chỉ được ghi và bỏ qua ở cấp gói, không giả thành hoàn thành. Lỗi runtime chung hoặc controller thoát sẽ dừng.
5. `MAX_UNITS` giữ giá trị cấu hình hiện có; đặt `None` để tiếp tục mọi gói còn thiếu. Không chạy đồng thời hai cell điều phối. Không chạy lại cell 2 của notebook cũ vì nó nạp runtime cũ.

Nếu runtime có sửa đổi làm anchor khác, cell dừng trước khi đổi file. Dùng notebook/runtime mới bên dưới thay vì ép vá. Bản vá có rollback cho lỗi ghi file và sao lưu nguyên runtime trước đó.

`COLAB_JSONL_REPAIR_CELL.txt` chỉ vá, không chạy queue; `COLAB_AUTO_SKIP_CELL.txt` là cell xử lý riêng nếu cần tách hai thao tác.

## Cho phiên Colab mới

- Upload `colab_orchestrator_v5_v6_jsonl_runtime.zip` vào `MyDrive/BKQuiz_cpt_data`.
- Mở `Colab_V6_L4_134_Units_JSONL_Fix.ipynb`, chọn Python 3/L4/High-RAM, chạy theo thứ tự. Dùng cùng `BKQuiz_v6_unit100` và bộ `inputs_134`.
- Runtime revision: `v6-jsonl-unicode-l4-20261023`. Bộ 134 input và schema kết quả không đổi. Notebook mới có cell auto-skip với danh sách loại trừ thủ công rỗng; lỗi vẫn được lưu để xử lý sau.
- Notebook/runtime cũ được giữ, có bản sao metadata tại `releases/before_jsonl_fix_20261023`.

## Phạm vi xác nhận

Đã chạy native extraction và đóng gói bằng core thật trên 100 trang IT4025, đối chiếu nguyên văn từng trang với native extraction và kiểm hash file bản ghi trước/sau đóng gói. Có kiểm thử Unicode, CRLF/BOM, file thật bị cắt, JSON liền nhau thiếu LF, alias import sớm, ZIP kết quả, vá lặp lại, bảo toàn sửa crop và rollback. Kết quả hồi quy được ghi ở `test_jsonl_evidence_20261023.json` và `tests_jsonl_20261023.txt`.

Chưa chạy OCR/Docling/Qwen thật hoặc notebook mới trên Colab trong đợt sửa này. Không suy ra chất lượng học thuật hoặc thời gian hoàn tất các gói còn lại từ kiểm thử parser.
