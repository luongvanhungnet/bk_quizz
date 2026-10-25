# IT3170 preprocessing v4

Bản dùng để chạy: **`runs/it3170_v4_20261019_final`**. Các run khác là bản dựng thử được giữ để truy vết. V1/v2/v3 không bị sửa.

V4 giữ Qwen2.5-VL-7B-Instruct NF4, thay đổi cách giao việc và kiểm định: ứng viên node/cạnh từ PDF được VLM kiểm tra, thuộc tính chia nhóm tối đa bốn cạnh, N-Queens đọc từng bàn cờ rồi nối cây. Không tự coi ứng viên native/CV hoặc output JSON hợp lệ là kiến thức đã xác minh.

## Chạy Colab Pro

1. Mở **`IT3170_Region_V4_7B.ipynb`** trên Google Colab, chọn GPU runtime.
2. Chạy từ đầu, upload **`runs/it3170_v4_20261019_final/region_v4_input.zip`** khi notebook hỏi. Giữ đúng tên file. Không dùng ZIP v3 hoặc ZIP trong các run thử.
3. Notebook kiểm tra hash và khôi phục môi trường VLM từ các archive theo Python tag trong `MyDrive/BKQuiz_preprocessing` khi tương thích. Phiên bản Python hỗ trợ 3.10–3.13; archive py313 chỉ được phục hồi khi phù hợp. Không cài Paddle vì toàn bộ specialist đã có seed.
4. Chạy **canary 930/1042** trước. Nó gồm 10 tác vụ nhỏ. Xem status và quality flags. Nếu không thành công cấu trúc, notebook không mở rộng sang phần pilot còn lại.
5. Khi canary đạt, chạy các cell pilot còn lại: hai crop cây trang 129, đồ thị 494 và 812. Tổng cả pilot là 39 tác vụ; canary đã thành công được dùng lại.
6. Xem raw output, ảnh nguồn và bằng chứng. Giữ `RUN_FULL=False` cho đến khi đã đối chiếu pilot. Sau đó có thể đặt `RUN_FULL=True`; worker yêu cầu đủ sáu parent pilot thành công cấu trúc, nhưng không tự xác minh ngữ nghĩa.
7. Chạy cell download ngay cả khi có lỗi. Tải ZIP `region_v4_results_...zip` về máy để đánh giá.

Output bền vững ở `MyDrive/BKQuiz_region_v4/results_<manifest hash>`, cache ở `MyDrive/BKQuiz_region_v4/task_cache`. Weights nằm ngoài archive venv, nên việc khôi phục môi trường không bảo đảm bỏ được thời gian tải weights.

## Giới hạn tài nguyên và tiếp tục sau lỗi

- Batch 1, profile chính tối đa 384 visual token, retry 256; crop nhỏ được phóng lên khoảng 64 visual token để không mất chi tiết bàn cờ do số patch quá ít.
- Text tối đa 2.048 token; toàn chuỗi kể cả output tối đa 4.096. Worker từ chối task vượt ngân sách thay vì cắt schema/text nguồn âm thầm.
- Giới hạn output riêng: inventory/nodes 768, attributes/edges/tree links 1.024, board 512 token.
- Tối đa hai lần suy luận cho mỗi task trong một lượt gọi. OOM, schema lỗi và output bị cắt đều lưu raw/traceback/telemetry; không cache thành công.
- `--retry-failed` tạo attempt mới, giữ nguyên attempt trước. Task thành công được tiếp tục từ disk/cache; chunk fallback rỗng không gọi model.
- Sau lỗi lặp lại, tải diagnostics và xử lý nguyên nhân trước khi chạy tiếp. Không chạy vòng retry vô hạn.

Có 330 task khai báo trên 57 vùng thuộc 56/1.060 trang (5,28%). Một số task fallback là slot động rỗng và sẽ được bỏ qua không suy luận. **Số trang thấp không đồng nghĩa ít lời gọi hoặc bảo đảm nhanh hơn v3.** Cần đo thời gian/VRAM thực trên Colab; cấu hình này chưa được chạy GPU tại máy hiện tại.

## Nhập và đánh giá kết quả tại máy

Chạy PowerShell từ `D:\BKQuiz`, thay tên ZIP thực tế:

```powershell
$py = 'AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe'
$v4 = 'AI\Qwen_cpt_version\region_preprocessing_v4'
$run = "$v4\runs\it3170_v4_20261019_final"
& $py "$v4\review.py" --run $run --results "$env:USERPROFILE\Downloads\region_v4_results_YOUR_RUN.zip" --out "$v4\reviews\colab_001"
& $py "$v4\evaluate.py" --run $run --results "$v4\reviews\colab_001\results.json" --out "$v4\reviews\colab_001\diagnostics.json"
```

Mỗi lượt nhập dùng thư mục review mới. Import kiểm tra task identity, hợp đồng đầu ra, seed specialist và tái ghép parent từ task evidence; không tự thêm CPT. Chấm bốn đồ thị vẫn dùng gold/metric cũ để so sánh với v2/v3. Bộ 60 trang chưa có nhãn chuẩn hoàn tất.

## Review công thức/bảng và xuất CPT

Mở `runs/it3170_v4_20261019_final/specialist_review.html`: có 120 công thức và ba bảng cần đối chiếu, kèm crop, native text và nhóm lỗi. `specialist_review_plan.jsonl` ghi định tuyến xử lý. Không chạy lại đầu vào lỗi giống hệt; chỉ rerun khi đã sửa crop/cấu hình có lưu hash, hoặc tạo transcript được kiểm tra nguồn.

V4 hiện giữ nguyên **224 mẫu CPT, 25.691 token** sau tách nhóm holdout; không có facts VLM mới. 40 mẫu được dành lại; bộ cũ 264 mẫu nằm trong `carried_cpt_archive`. Chia lại không xóa sự tiếp xúc của checkpoint CPT cũ với các trang này.

Xem [ANNOTATION_GUIDE.md](ANNOTATION_GUIDE.md). Khi đã có bản chép được đối chiếu nguồn, dùng:

```powershell
& $py "$v4\annotations.py" export-cpt --run $run --reviews "$v4\annotations\verified_transcripts.jsonl" --out "$v4\datasets\reviewed_001"
```

Export chặn trang thuộc nhóm holdout, nguồn/hash sai và thiếu người duyệt/bằng chứng. Schema pass, model confidence và quality gate không thay thế việc duyệt nội dung.

## Kiểm tra tại máy

```powershell
& $py -m unittest discover -s $v4 -p test_v4.py -v
& $py "$v4\local_audit.py"
```

[REPORT.md](REPORT.md) trình bày thay đổi, số liệu kỹ thuật và giới hạn. Audit tích hợp dùng **model giả**, chỉ kiểm tra luồng và việc không tự nâng trạng thái verified; không được dùng làm điểm chính xác của Qwen.
