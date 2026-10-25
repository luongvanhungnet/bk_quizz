# Tiếp tục input 7/14: Docling checkpoint không có thư mục output

## Đọc log

Lỗi trực tiếp:

```text
FileNotFoundError: .../batch_restore/53296f7b00c115de9162/output
orchestrator.py → execute_stage → shutil.copytree(restore/'output', batch_out)
```

Đang ở `it4025_ff432ad5e84a_p00001-00100:discovery:docling`, trong **input 7/14**. Đây là lỗi khi khôi phục đầu ra một nhóm Docling đã có checkpoint. Log không ghi CUDA out-of-memory hoặc runtime crash.

Code cũ đóng checkpoint bằng cách liệt kê **file**, không lưu thư mục rỗng. Nếu worker Docling lỗi trước khi ghi file, ZIP vẫn có manifest con, PDF con và phản hồi lỗi trong `batch.json`, nhưng không có member `output/...`. Lúc tiếp tục, code lại giả định `output` luôn tồn tại và gọi `copytree` vô điều kiện. Đó là trường hợp đã tái hiện được bằng regression test.

Traceback người dùng cung cấp chưa chứa phản hồi lỗi Docling ban đầu; vì vậy chưa thể kết luận nguyên nhân Docling không tạo được đầu ra là trọng số cache, dữ liệu trang, môi trường hay tài nguyên. Cell khôi phục mới in phản hồi gốc và số file output trong checkpoint để phân biệt hai lớp lỗi.

File sau đã được sao chép và kiểm SHA-256 trên Drive:

```text
BKQuiz_v5_drive_v3/downloads/v5_drive_diagnostics_upload_07_1792651346971515835.zip
1.552.377.731 byte
68ccb25b12ffb5de727a8d0932fe328cc748eab96c3971d6b0102543e7c401fc
```

Đây là **ZIP chẩn đoán**, không phải kết quả input 7 đã hoàn thành. Không dùng nó để commit input 7 hoặc đánh dấu training-ready. Không cần tải toàn bộ file này để áp dụng bản vá.

## Cách tiếp tục ngay trong phiên Colab hiện tại

1. Qua Google Drive, upload **`colab_orchestrator_v3_l4_batchfix_runtime.zip`** vào **MyDrive/BKQuiz_cpt_data** cùng 14 input cũ.
2. Mở **`COLAB_RESUME_INPUT7_CELL.txt`** trên máy, chép toàn bộ nội dung vào **một cell mới trong notebook đang chạy**, rồi chạy cell đó sau khi cell lỗi đã kết thúc.
3. Cell kiểm SHA runtime, hiển thị `last_acknowledged_index` và phản hồi Docling gốc của checkpoint liên quan. Nó đóng controller cũ, giữ venv/file Drive, rồi khởi động controller đã vá từ một thư mục runtime riêng. Không chạy pip và không yêu cầu restart VM khi venv hiện tại còn.
4. Cell lấy input kế tiếp từ state thực tế; với trạng thái của log này thường là input 7. Các stage/checkpoint đã có tiếp tục được dùng lại. Chỉ commit sau khi ZIP kết quả thật đã lưu và kiểm hash trên Drive.
5. Cell chạy tối đa một input. Chạy lại chính cell này để xử lý input kế tiếp; controller đã vá còn sống sẽ được dùng lại. Không chạy lại bootstrap cũ của notebook sau khi áp dụng cell.

Nếu runtime/venv đã mất, mở **`Colab_V5_L4_Resume14_BatchFix.ipynb`** thành một bản riêng, chọn L4/High-RAM/Python 3 và chạy tuần tự. Dùng runtime ZIP batchfix ở bước 1 và giữ **BASE cũ `BKQuiz_v5_drive_v3`** để nhận tiến độ. Không chạy đồng thời hai queue cùng BASE.

Không xóa `queue_state.json`, `page_batches`, checkpoint, model cache hoặc kết quả trước đó để xử lý lỗi này. Bản vá tiếp tục đúng **bộ 14 input**. Bộ điều phối 134 gói vẫn là kế hoạch vận hành riêng.

## Bản vá thay đổi gì

- Đọc manifest sau khi kiểm hash archive và từng member; xác minh checkpoint khớp stage/phản hồi đã lưu.
- Nếu có file `output/...`, khôi phục như trước.
- Nếu không có output và checkpoint đã ghi **lỗi**, tạo thư mục chứa ghi chú kiểm toán, giữ nguyên phản hồi/traceback gốc, không tạo kết quả Docling giả và không chạy lại inference chỉ vì thư mục rỗng bị thiếu.
- Nếu checkpoint tự báo **thành công** nhưng không có output, dừng với lỗi rõ ràng để xử lý/rerun có kiểm soát; không coi nó là kết quả hợp lệ.
- Bỏ qua thư mục output cũ nằm ngoài inventory, kiểm marker theo SHA và kiểm ranh giới thư mục trước khi dọn staging cục bộ.

Nếu Paddle layout đủ coverage, pipeline có thể tiếp tục với lỗi Docling đã ghi. Nếu không đủ, job vẫn bị chặn. `all_stages_successful` không được nâng thành true vì phục hồi hết FileNotFoundError; human review/CPT gate giữ nguyên.

Các ZIP checkpoint, manifest, hash và output trước được giữ nguyên. Bản trước vá nằm tại `releases/before_batch_output_fix_20261022`. Cùng lỗi ở thư viện điều phối v4 cũng được vá; không dựng lại 134 input.

## Kiểm thử

`test_batch_restore.py` kiểm tra checkpoint lỗi không có output, process hoàn thành nhưng result lỗi, checkpoint tự báo thành công rỗng, thư mục output cũ ngoài inventory, khôi phục output bình thường và tiếp tục pipeline sau Docling lỗi mà không inference lại hoặc đổi trạng thái thành công. Có thêm kiểm tra pin runtime/cell khôi phục và giữ BASE 14 input.

Đã chạy **42 kiểm thử, đều đạt**, trong 73,781 giây; log đầy đủ nằm trong `tests_batchfix_20261022.txt`. Thư viện điều phối v4 nhận cùng bản vá và đạt 15/15 kiểm thử. Core v5 chính thức vẫn khớp 48/48 hash. Các kiểm thử dùng backend mô phỏng cho inference; bản vá chưa được chạy trên phiên Colab thực tế của người dùng. Bản này sửa lỗi khôi phục checkpoint; không khẳng định lỗi Docling ban đầu đã được sửa.
