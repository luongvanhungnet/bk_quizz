# v5 — 14 input cân bằng, xử lý và tải kết quả từng file

Core dữ liệu vẫn là **v5.0.0**. Lớp vận hành mới là **v5-orchestrator-2-sequential**. Dùng bộ input mới; các file `v5_upload_...` và notebook v1 được giữ để đối chiếu, không dùng trong lượt tuần tự này.

## File cần dùng

- [Notebook Colab tuần tự](Colab_V5_Sequential_14.ipynb).
- [Danh sách 14 ZIP input mới](../uploads_14_sequential_20261021/UPLOAD_LIST.md).
- [Danh mục dung lượng, hash và thống kê phương sai](../uploads_14_sequential_20261021/UPLOAD_INDEX.json).

## Cách chạy

1. Mở notebook mới trên Colab GPU.
2. **Cell 1:** kết nối Drive, dùng `BASE=MyDrive/BKQuiz_v5_sequential`. Cell này không upload.
3. **Cell 2:** chọn đúng **một** file `v5_sequential_01_of_14.zip`. Không cần upload trước file 02–14.
4. **Cell 3:** xác minh runtime được khóa hash.
5. **Cell 4:** khôi phục/cài môi trường một lần. Dùng lại các môi trường và cache cũ khi tương thích.
6. **Cell 5:** xử lý file hiện tại, xuất ZIP kết quả và gọi tải xuống. **Sau khi trình duyệt đã tải xong**, gõ `DA_TAI`. Notebook mới mở hộp thoại chọn file 02. Lặp đến 14.

Nếu gõ `DUNG` hoặc không xác nhận `DA_TAI`, notebook giữ ở kết quả hiện tại. Nó chỉ biết bạn đã yêu cầu tải và nhập xác nhận; không tự kiểm tra thư mục Downloads để khẳng định tải xong.

Phải đi đúng thứ tự **01 → 02 → … → 14**, vì PDF dùng chung và các phần cache đã nhận được giữ trên Drive/checkpoint để gói sau dùng lại. Không cần dữ liệu của một input trong tương lai để thực thi input hiện tại.

## Cân bằng dung lượng mà giữ nguyên dữ liệu

- Các học phần mới được gom **trọn học phần** vào một input, gồm toàn bộ job discovery/inference. Điều này giữ routing budget theo toàn học phần và tránh phải đợi input sau mới đủ layout.
- IT3170 dùng layout/cache có sẵn nên có thể chia theo các nhóm trang gốc. Record, ảnh render, ảnh crop, ảnh context và specialist seed được phân bổ theo nhóm trang.
- Bộ chia dùng **Longest Processing Time theo số byte nén ước tính**, lần lượt đưa đơn vị dữ liệu lớn nhất vào gói hiện nhẹ nhất. PDF nguồn IT3170 dùng chung được đặt ở input 01.
- File ảnh và PDF được giữ nguyên byte/hash. Không giảm độ phân giải, không chuyển JPEG và không sinh lại dự đoán cache chỉ để cân bằng gói.
- Seed fragment chỉ thêm record chưa có. Khi một record đã được xử lý, fragment đến sau không ghi đè candidate mới bằng bản cache cũ.
- 27 PDF / 13.314 trang / 148 gói con vẫn giữ nguyên. Dung lượng input cân bằng hơn không đồng nghĩa thời gian xử lý từng input bằng nhau.

## Model và môi trường giữa các input

Môi trường được chuẩn bị ở cell riêng, ngoài vòng lặp upload. Controller và worker Qwen là tiến trình sống xuyên các lần upload. Trong mỗi input, Paddle/layout chạy trước VLM. Giữa hai input, Qwen chuyển trọng số sang CPU, giải phóng tensor GPU để Paddle của lượt tiếp theo sử dụng; khi đến VLM, trọng số được chuyển lại GPU, không gọi lại `from_pretrained`.

Việc di chuyển thiết bị giữ nguyên dtype/NF4, dựa trên API ở phiên bản đã khóa: [bitsandbytes 0.48.1](https://github.com/bitsandbytes-foundation/bitsandbytes/blob/0.48.1/bitsandbytes/nn/modules.py), [Transformers 4.57.6](https://github.com/huggingface/transformers/blob/v4.57.6/src/transformers/modeling_utils.py). Đây là cơ sở triển khai, **chưa phải xác nhận chạy thành công trên GPU Colab**. Cần RAM CPU đủ giữ model trong lúc chạy các nhánh khác.

Mặc định `KEEP_MODEL_RESIDENT=True`. Nếu môi trường thực tế không hỗ trợ chuyển model hoặc thiếu RAM, có thể đặt `False` để giải phóng model sau từng input; khi đó model được nạp lại cho input tiếp, môi trường không phải cài lại. Nếu đổi sau khi Session đã khởi động, chạy:

```python
SESSION.close()
del SESSION
KEEP_MODEL_RESIDENT = False
```

Sau đó chạy lại cell 5. Không tự đổi chế độ hoặc tự coi lỗi GPU là thành công. Worker kiểm tra bộ nhớ tensor GPU sau khi chuyển sang CPU và từ chối mở Paddle nếu vẫn còn quá nhiều bộ nhớ do Qwen giữ.

## Tiếp tục khi Colab bị ngắt

Giữ cùng BASE. Chạy lại từ cell 1; cell input tìm lại file đang xử lý/chưa xác nhận tải trên Drive. Các stage đã hoàn thành và cache từng ảnh được dùng lại. Nếu kết quả đã xuất, notebook trả lại ZIP đã có thay vì chạy lại inference. Sau khi tải xong và nhập `DA_TAI`, mới chuyển sang input kế tiếp.

Runtime mới vẫn phải nạp model lại; RAM/GPU không tồn tại qua reset. Checkpoint ZIP delta giữ các run/ảnh/revision; danh sách input đã nhận giúp khôi phục các nguồn/cache cần thiết từ những file trước. File trong tương lai không được yêu cầu.

Lỗi được giữ trong `queue_state.json`, log và ZIP diagnostics trên Drive. Nếu input thiếu layout hợp lệ và bị chặn, nó không được đánh dấu hoàn thành hoặc mở upload kế tiếp. Với lỗi riêng từng vùng, kết quả lỗi vẫn được giữ cho kiểm duyệt, không tự xuất sang CPT.

## Nhập kết quả về máy

Giữ một ZIP `v5_results_upload_XX_*.zip` cho mỗi input. Dùng **importer v2** vì snapshot IT3170 tăng dần qua nhiều input. Có thể nhập đủ 14 file sau khi hoàn tất; khi có nhiều snapshot của cùng học phần, importer chọn snapshot sau có đủ record trước đó và kiểm tra danh tính nguồn/ảnh không thay đổi.

```powershell
Set-Location D:\BKQuiz
$py = 'AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe'
$returned = @(Get-ChildItem -LiteralPath 'AI\data_preprocessing\colab_returns' -Filter 'v5_results_upload_*.zip' | ForEach-Object { $_.FullName })
& $py -X utf8 AI\data_preprocessing\colab_orchestrator_v2\import_returns.py `
  --plan AI\data_preprocessing\plans\corpus_20261021 `
  --bundle-index AI\data_preprocessing\uploads_14_sequential_20261021\UPLOAD_INDEX.json `
  --results $returned --check-only
```

Khi kiểm tra đạt, dùng cùng lệnh và bỏ `--check-only` để nhập. Không chọn hai ZIP khác nhau cho cùng một input nếu snapshot đã thay đổi. SQLite kiểm duyệt tại máy được giữ; không tự tạo approval và không xuất CPT. Kiểm duyệt vẫn chỉ hiển thị VLM thành công, dùng ←/→, ↑, ↓ và nút Sửa như trước.

## Kiểm thử

Lệnh:

```powershell
& $py -X utf8 -m unittest discover -s AI\data_preprocessing\colab_orchestrator_v2 -p 'test_*.py' -v
```

9/9 test đạt tại máy: thứ tự upload/tải/xác nhận, cân bằng, seed tăng dần, giữ candidate đã xử lý, dùng chung worker/model, tiếp tục sau reset, xuất và nhập hai lượt cùng snapshot tăng dần. Inference được mô phỏng; mapping, packaging, validation, checkpoint, export/import dùng core v5 thật. Chưa benchmark GPU hoặc độ chính xác dữ liệu mới.
