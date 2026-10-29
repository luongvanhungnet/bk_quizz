# Runbook thực thi corpus — v5 chính thức

Phạm vi đã kiểm kê: **27 PDF, 13.314 trang**. Kế hoạch có **148 shard**, tối đa 100 trang/shard. IT3170 dùng run/cache đã có; 26 học phần khác cần discovery trước inference. Đây là kế hoạch thực thi, không phải thông báo toàn corpus đã được làm sạch.

## 1. Đường dẫn cố định

```powershell
Set-Location D:\BKQuiz
$py = 'AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe'
$entry = 'AI\data_preprocessing\manage.py'
$plan = 'AI\data_preprocessing\plans\corpus_20261021'
$work = 'AI\data_preprocessing\workspaces\corpus_20261021'
& $py -X utf8 $entry verify
& $py -X utf8 $entry preflight --plan $plan
```

`verify` kiểm hash từng file snapshot chính thức trước khi chạy. `preflight` kiểm SHA các PDF, mỗi source page xuất hiện đúng một lần trong kế hoạch và ngưỡng dung lượng trống. Nếu nguồn đã đổi, tạo inventory/plan mới; không sửa plan cũ cho khớp file mới.

- Đặc tả: `SPEC_V5_OFFICIAL.md` cạnh tài liệu này.
- Inventory: `catalogs/corpus_20261021/documents.csv` và `documents.jsonl`.
- Jobs: `plans/corpus_20261021/jobs.jsonl`.
- Chỉ định release: `CURRENT.json`; cấu hình: `production.json`.
- Notebook corpus: `AI/Qwen_cpt_version/region_preprocessing_v5_official/Colab_V5_Official_Corpus.ipynb`.
- `START_HERE.md` ghi packet đầu tiên thực tế đã chuẩn bị và hash của nó.

## 2. Chạy tiếp IT3170 từ cache

Không render lại 1.060 trang hoặc xóa các quyết định trong web. Các shard đều trỏ về run v5 đã nhận kết quả pilot.

```powershell
& $py -X utf8 $entry prepare --plan $plan --document IT3170
& $py -X utf8 $entry package --plan $plan `
  --job-id it3170_c6c829f14bf2_p00001-00100 --phase inference
```

Để đóng cả 11 shard IT3170:

```powershell
& $py -X utf8 $entry package --plan $plan --document IT3170 --phase inference
```

Thư mục packet in ra trên terminal có `manifest.json` và `v5_colab_input.zip`. Các công thức/bảng seed hợp lệ được giữ; lỗi cũ trên crop không đổi được deferred, không tự chạy lại mù quáng. Cache VLM thành công chỉ được dùng lại nếu input/context/prompt/model/runtime khớp.

## 3. Học phần mới: native và discovery

Ví dụ IT3011:

```powershell
& $py -X utf8 $entry prepare --plan $plan --document IT3011
& $py -X utf8 $entry package --plan $plan --document IT3011 --phase discovery
```

Lệnh đầu render/native toàn học phần, lệnh sau chia packet 100 trang. Discovery cần OCR, PP-Structure layout và Docling; chưa chạy Qwen. Không dùng `--phase inference` để bỏ qua bước này: controller sẽ chặn khi `layout_inventory_status` chưa ready.

Để chuẩn bị local cho tất cả tài liệu, chạy tuần tự:

```powershell
& $py -X utf8 $entry prepare --plan $plan --all-documents
& $py -X utf8 $entry package --plan $plan --all-documents --phase discovery
```

Hai lệnh này có thể tạo nhiều ảnh/gói. Đã có checkpoint theo tài liệu; sau lỗi, phần có manifest/source đúng được dùng lại. Thư mục prepare dở không được tự coi hoàn thành hoặc bị xóa. Giữ lại để điều tra, rồi dùng work_root mới cho tài liệu đó nếu cần.

Giữ nguồn `D:\bk_quizz_data` chỉ đọc; mọi output mới nằm trong `AI/data_preprocessing/workspaces/`. Không dùng bản giải nén trong `_work` như tài liệu độc lập để tránh nạp lại nguồn nhiều lần.

## 4. Colab: thực thi một packet

1. Mở notebook **`Colab_V5_Official_Corpus.ipynb`** từ snapshot chính thức, chọn GPU.
2. Để `INPUT_ZIP=None` và upload đúng **một** `v5_colab_input.zip`, hoặc đặt đường dẫn Drive chính xác. Notebook không tự tái dùng một file cũ chỉ vì có cùng tên.
3. Kiểm tra manifest hash, scope, phase và job trước khi chạy. Packet discovery/inference tự chọn stage; không cần mở VLM cho discovery.
4. Chạy các cell theo thứ tự. Các env khôi phục từ archive Python tag khi tương thích. Dùng lại HF/Paddle/VLM success cache của v5 trên Drive; mỗi engine chạy process riêng.
5. Chạy cell đóng ZIP kể cả khi một engine lỗi. Tải `region_v5_results_<packet hash>_<attempt>.zip`.

Đường dẫn bền vững: `MyDrive/BKQuiz_preprocessing_v5/results_<manifest hash>`. Cache dùng lại từ `MyDrive/BKQuiz_region_v5`. Archive venv ở `MyDrive/BKQuiz_preprocessing`. Không xóa cache của các phiên bản trước.

Notebook hiện chạy **một packet mỗi lượt**, không tự tải 285 packet hoặc tự quản lịch Colab ngoài session. Có thể làm lần lượt theo job list, giữ cùng runtime để tái dùng môi trường/cache. Thời gian khởi tạo model và tài nguyên giữa các packet vẫn phải đo; không giả định throughput pilot áp dụng cho mọi môn.

## 5. Nhập kết quả đúng job

Lấy `job_id` từ tên folder hoặc `manifest.json`. `--packet` trỏ đến folder có manifest, không trỏ đến ZIP. Ví dụ:

```powershell
$job = 'IT3011_JOB_ID_TU_MANIFEST'
$packet = 'DUONG_DAN_FOLDER_PACKET_DA_UPLOAD'
$results = "$env:USERPROFILE\Downloads\TEN_ZIP_KET_QUA.zip"
& $py -X utf8 $entry merge --plan $plan --job-id $job `
  --packet $packet --results $results
```

Controller kiểm source/packet/request/hash. Với discovery, sau import sẽ materialize vùng mới, lưu raw/unmapped và cập nhật `layout_pages_processed`. Khi đủ mọi shard của một học phần, trạng thái kỹ thuật layout thành ready. Nếu một parser lỗi hoặc không có output hợp lệ, không được tự mở inference cho tài liệu chưa đủ layout.

Sau mỗi merge, xem:

- `manifest.json`: source và tiến độ layout.
- `machine_summary.json`: ba nhóm máy; không phải accuracy.
- `routing_summary.json`: trang/crop được chọn VLM, deferred, quy tắc trang trí/trùng.
- `import_receipts/`: lỗi bbox/page và vùng chưa thể so sánh.
- `events.jsonl` tại work_root: lịch sử prepare/package/merge.

Nếu chỉ muốn tiếp tục các môn đã có layout, chọn riêng `--document`, không đổi phase của packet discovery rồi gửi lại như inference.

## 6. Inference sau discovery

```powershell
& $py -X utf8 $entry package --plan $plan --document IT3011 --phase inference
```

Upload các packet mới vào notebook corpus, nhập ZIP trả về như bước 5. Formula/table chỉ nhận vùng đúng loại; VLM chỉ nhận các vùng đã định tuyến. Tỷ lệ trang VLM được tính trên toàn tài liệu, không trên riêng một shard có nhiều hình.

Khi toàn bộ học phần mới đã ready, có thể đóng các packet inference còn lại:

```powershell
& $py -X utf8 $entry package --plan $plan --all-documents --phase inference
```

Không có thao tác nào ở bước này tự tạo human approval hoặc tự đưa prediction mới vào CPT.

## 7. Human Review chỉ VLM

```powershell
& $py -X utf8 $entry review --plan $plan --document IT3011 --port 8766
```

Mỗi app mở một học phần/run; dùng cổng khác khi web IT3170 đang ở 8765. IT3170 có shortcut:

```powershell
& $py -X utf8 $entry review-it3170 --port 8765
```

Nếu app đang chạy sẵn, mở URL hiện có thay vì khởi tạo server thứ hai ở cùng cổng.

- Nhập tên thật một lần; **← / →** chuyển mục, **↑** chấp nhận, **↓** loại.
- **Sửa** mở editor; lưu bản sửa khi đã đối chiếu slide.
- Chỉ text VLM thành công có trong queue. Native/OCR và specialist không có VLM vẫn được lưu ở kiểm kê, không bị giả xác minh.
- Phím tắt tạm dừng khi gõ/sửa/tải ảnh/lưu; giữ phím không ghi nhiều quyết định.
- Chỉ duyệt phần thật sự đọc rõ; số trang, footer và diễn giải không có bằng chứng cần sửa/loại.

## 8. Dataset và split trước huấn luyện

Giữ group/split cũ IT3170. Với học phần mới, toàn học phần cùng group; `course_splits` mặc định chưa tạo test corpus độc lập. Trước khi train/đánh giá kết hợp phải chốt holdout theo học phần/nhóm và audit near-duplicate liên tài liệu. Không chia ngẫu nhiên các slide gần trùng.

Export hiện tại chỉ lấy transcript approve/correct còn hiệu lực thuộc train. Tham khảo lệnh `cli.py export` của snapshot chính thức. Web chỉ duyệt VLM không đồng nghĩa native/OCR đã được người duyệt hoặc tự đủ điều kiện train. Controller không cung cấp một lệnh “export tất cả” để vượt các gate còn thiếu.

Không chấm Q hoặc accuracy bằng tỷ lệ API/schema pass. Tạo human-reference subset nguồn đúng hash nếu cần CER/WER/groundedness/coverage. Dùng `METRICS.md` và `evaluate_run.py` của release.

## 9. Quản lý phiên bản và sự cố

- `CURRENT.json` chọn v5.0.0. Không sửa mã trong `region_preprocessing_v5_official`; controller sẽ báo hash sai.
- Mã thử nghiệm tiếp tục ở `region_preprocessing_v5`, không tự ảnh hưởng release đã chốt. Thay đổi hành vi sản xuất phải phát hành version mới và cập nhật CURRENT sau kiểm thử.
- Không dùng `pip install -U` chung vào env VLM/Paddle. Lưu freeze sau mỗi lượt Colab; đọc lỗi và xác minh compatibility trước khi thay package.
- Parser/VLM lỗi: giữ ZIP, log, trace, raw, GPU info. Không sửa output thành “ok” hoặc “verified” để tiếp tục.
- Đổi ảnh/crop/context hoặc nguồn khiến review cũ stale. Hãy kiểm source hiện tại thay vì tái sử dụng approval sai bằng chứng.
- Packet vượt 512 MiB: giảm pages_per_packet trong cấu hình mới và tạo plan mới. Không cắt trang âm thầm.

## 10. Trạng thái chuẩn bị đã hoàn thành

Đã có inventory 27/27 nguồn, plan 148 shard, snapshot v5.0.0 và đặc tả này. Source PDF chưa bị sửa. Chưa render mới 12.254 trang của 26 học phần khác và chưa chạy cloud inference toàn corpus. Packet mở đầu IT3170 được chuẩn bị từ cache; xem `START_HERE.md` để bắt đầu bằng một gói cụ thể đã kiểm tra.
