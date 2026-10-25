# IT3170 region preprocessing v3

Kết quả Colab đã được đánh giá: [báo cáo so sánh v1/v2/v3](evaluation_aa4973c0f29f/REPORT.md). Lượt này có 1/6 crop pilot VLM hợp lệ; cần sửa lỗi schema và OOM trước khi chạy đầy đủ.

Bản phát hành dùng thư mục `runs/it3170_v3_20261019`. Dữ liệu v1/v2 được giữ nguyên. Các thư mục run khác trong v3 là bản thử nội bộ được giữ để truy vết.

## Chạy trên Google Colab Pro

1. Mở `IT3170_Region_V3_7B.ipynb` trong Colab, chọn GPU runtime.
2. Chạy các cell từ đầu; khi được yêu cầu, tải lên **`runs/it3170_v3_20261019/region_v3_input.zip`**. Không dùng ZIP đầu vào v2.
3. Notebook gắn Drive, kiểm tra hash, khôi phục môi trường phù hợp từ `MyDrive/BKQuiz_preprocessing` nếu có, rồi kiểm tra/cài các phiên bản còn thiếu. Venv lưu trước đó chỉ được dùng khi phiên bản Python phù hợp. Model và cache suy luận vẫn cần được tải/kiểm tra riêng.
4. Gói này có seed cho toàn bộ nhánh công thức/bảng nên mặc định bỏ qua cài/khôi phục Paddle. Chỉ môi trường VLM cần chạy. Model là **Qwen2.5-VL-7B-Instruct**, NF4, batch 1, SDPA; revision `cc594898137f460bfe9f0759e9844b3ce807cfb5`.
5. Giữ `RUN_FULL = False` ở lượt đầu: chạy 6 crop thuộc 5 trang khó (129, 494, 812, 930, 1042). Có 14 lời gọi model vì đồ thị được tách thành ba bước. Xem output/crop và các cảnh báo trước khi bật `RUN_FULL = True`. Worker chặn lượt đầy đủ nếu pilot chưa vượt kiểm tra cấu trúc.
6. Chạy cell thu thập/đóng ZIP kết quả. Output bền vững nằm trong `MyDrive/BKQuiz_region_v3/results_aa4973c0f29f`. Tải ZIP `region_v3_results_...zip` về máy.

Toàn bộ lịch VLM gồm 57 crop trên 56/1.060 trang (5,28%): 55 đồ thị và 2 cây trạng thái. Khi không có cache, lịch đầy đủ có 167 lời gọi; pilot là một phần của lịch này. Không áp dụng ước lượng 30 giây/trang cũ cho cấu hình ba bước. Thời gian/VRAM thực tế cần đo trên runtime Colab được cấp.

Cache hợp lệ được dùng lại theo hash ảnh, context, cấu hình và đầu ra bước trước. Kết quả lỗi được giữ để điều tra nhưng không trở thành cache thành công. Khi thử lại sau lỗi, dùng thư mục output lượt mới và giữ cache Drive chung. Không sửa đè snapshot đã tồn tại.

## Nhập kết quả và đánh giá trên máy

Chạy PowerShell tại `D:\BKQuiz` (thay tên ZIP thực tế):

```powershell
$py = 'AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe'
$v3 = 'AI\Qwen_cpt_version\region_preprocessing_v3'
$run = "$v3\runs\it3170_v3_20261019"
& $py "$v3\review.py" --run $run --results "$env:USERPROFILE\Downloads\region_v3_results_YOUR_RUN.zip" --out "$v3\reviews\colab_v3_001"
& $py "$v3\evaluate.py" --run $run --results "$v3\reviews\colab_v3_001\results.json" --out "$v3\reviews\colab_v3_001\diagnostics.json"
```

Chọn tên thư mục review mới cho mỗi lần nhập. `prediction_review.jsonl` chứa kết quả, lỗi schema và cảnh báo chất lượng; không tự ghi thêm dữ liệu train. `diagnostics.json` dùng lại định nghĩa metric trên bốn đồ thị phát triển của v2. Đây không phải đánh giá holdout độc lập.

## Bộ chuẩn đánh giá và duyệt CPT

Mở `runs/it3170_v3_20261019/benchmark_review.html` để xem 60 trang và thông tin nguồn. `benchmark_queue.jsonl` hiện **chưa có nhãn chuẩn**: 42 trang development, 18 trang holdout. Không dùng ảnh/nhãn holdout để chỉnh prompt hoặc luật. Có 14 trang đồ thị dưới ngưỡng định tuyến để kiểm tra nội dung bị bỏ sót.

Hướng dẫn tạo nhãn: [ANNOTATION_GUIDE.md](ANNOTATION_GUIDE.md). Khi đã có JSONL nhãn được đối chiếu nguồn:

```powershell
& $py "$v3\annotations.py" check-benchmark --run $run --reviews "$v3\annotations\gold.jsonl" --out "$v3\annotations\routing_metrics.json"
& $py "$v3\evaluate.py" --run $run --results "$v3\reviews\colab_v3_001\results.json" --annotations "$v3\annotations\gold.jsonl" --out "$v3\reviews\colab_v3_001\benchmark_metrics.json"
```

Schema hợp lệ, heuristic pass và confidence của model **không đồng nghĩa đã xác minh ngữ nghĩa**. Công thức/bảng tái sử dụng và mọi dự đoán VLM đều vào review. Chỉ transcript được người duyệt đối chiếu nguồn rõ ràng mới được xuất thêm CPT:

```powershell
& $py "$v3\annotations.py" export-cpt --run $run --reviews "$v3\annotations\verified_transcripts.jsonl" --out "$v3\datasets\reviewed_001"
```

`cpt/` hiện chỉ chứa 224 mẫu kế thừa sau loại nhóm holdout, 25.691 token, 26 chuỗi tối đa 1.024 token. Bản 264 mẫu cũ giữ trong `carried_cpt_archive/`; 40 mẫu dành lại được ghi riêng trong metadata. Đây chưa phải dữ liệu đầy đủ của toàn bộ học phần. Checkpoint CPT trước đây đã học bộ cũ có thể đã thấy các trang vừa được dành lại; việc chia lại không xóa sự tiếp xúc đó.

## Kiểm tra tại máy

```powershell
& $py -m unittest discover -s $v3 -p test_v3.py -v
& $py "$v3\local_audit.py"
```

Kết quả hiện tại và giới hạn: [REPORT.md](REPORT.md). Gói GPU ZIP chỉ chứa crop/context/seed/code; bộ nhãn và CPT ở máy để quản lý tách biệt.
