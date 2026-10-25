# IT3170 preprocessing v2 — Qwen2.5-VL-7B

Đợt sử dụng: **`runs/it3170_v2_release`**. Không dùng các thư mục `it3170_v2`/`it3170_v2_candidate` là bản dựng thử. Bản cũ tại `../region_preprocessing` được giữ nguyên.

**Đã nhận kết quả Colab:** xem [đánh giá thực tế đợt d682e3b25b0d](evaluation_d682e3b25b0d/REPORT.md). ZIP này có 5 crop VLM/model, còn 51 crop 7B chưa chạy; không coi là hoàn thành toàn bộ lịch VLM.

Đã sửa prompt/schema, tái kiểm định output 3B cũ không inference, sửa và thử thành công 16 bảng bằng CPU, tách crop công thức khỏi đoạn văn/bảng. Chi tiết số đo và giới hạn: [REPORT.md](REPORT.md).

## Chạy trên Colab

1. Mở **[IT3170_Region_V2_7B.ipynb](IT3170_Region_V2_7B.ipynb)** bằng Google Colab, chọn GPU T4 hoặc tốt hơn.
2. Ở cell upload, chọn đồng thời hai file:
   - [region_v2_3B_input.zip](runs/it3170_v2_release/region_v2_3B_input.zip).
   - [region_v2_7B_input.zip](runs/it3170_v2_release/region_v2_7B_input.zip).
3. Chạy từ trên xuống. Notebook tìm bản sao venv tại `MyDrive/BKQuiz_preprocessing/it3170_*_env_py313_v1.tar.gz` nếu runtime Python khớp, giữ đúng đường dẫn `/content/it3170_paddle_env` và `/content/it3170_vlm_env`. Cài bổ sung bitsandbytes nếu thiếu; không khẳng định model weights đã nằm trong archive venv.
4. Thứ tự bắt buộc: **table canary → specialist batch → baseline 3B trên 5 trang khó → pilot 7B cùng 5 trang → 7B phần còn lại**. Cổng schema lỗi sẽ dừng trước mở rộng; đọc raw output/traceback, không tự sửa fact.
5. Tải `region_v2_results_d682e3b25b0d.zip` về. Drive lưu kết quả ở `MyDrive/BKQuiz_region_v2/`, tách khỏi các đợt trước.

Model mặc định `Qwen/Qwen2.5-VL-7B-Instruct`, revision đã khóa. Cả baseline 3B và 7B dùng **NF4, FP16 compute, batch 1, SDPA, 768 visual token, max_new_tokens=2048**, cùng prompt và ảnh. Không bảo đảm vừa VRAM/tốc độ trước khi chạy Colab thực tế; lỗi khởi tạo/OOM được lưu đầy đủ.

16 bảng CPU đã chạy được đưa vào seed có hash; 10 kết quả FormulaNet cũ còn đúng điều kiện được dùng lại. Vì vậy table canary có thể báo **Reusing valid canary record**: đang dùng kết quả đã thử thành công, không phải bỏ qua lỗi cũ. Chưa chạy lại bảng trên GPU Colab; seed CPU vẫn chưa được duyệt nội dung.

Nếu cần thử lại một lần inference lỗi, giữ thư mục output thất bại và chọn tên attempt mới trong `OUTPUTS`, không xóa hay sửa record đã lưu. Không chỉnh model/prompt trực tiếp trong ZIP; thay cấu hình phải dựng một plan mới để đổi hash/cache key.

## Nhập kết quả về máy

Từ `D:\BKQuiz`, chạy:

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\region_preprocessing_v2\review_results.py --run AI\Qwen_cpt_version\region_preprocessing_v2\runs\it3170_v2_release --results "$env:USERPROFILE\Downloads\region_v2_results_d682e3b25b0d.zip" --out AI\Qwen_cpt_version\region_preprocessing_v2\reviews\colab_v2_001
```

Lệnh tạo `3B_prediction_review.jsonl`, `7B_prediction_review.jsonl`, diagnostics theo nguồn và `summary.json`. Từ chối sai manifest/cache/pixel identity. **Không ghép prediction vào CPT.** Tất cả record dẫn xuất đều `semantic_verified=false`, `destination=review_queue`, kể cả khi model trả về trường tự nhận đã xác minh.

Bộ CPT kế thừa nằm tại `runs/it3170_v2_release/cpt/`: 264 mẫu, 29.771 token. Chưa có CPT mới từ VLM/FormulaNet/table. Cần đối chiếu nguồn và transcript được duyệt trước khi tạo một phiên bản dataset tiếp theo.

## Kiểm thử và dựng lại

```powershell
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe -m unittest discover -s AI\Qwen_cpt_version\region_preprocessing_v2 -p test_v2.py -v
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\region_preprocessing_v2\revalidate.py
AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe AI\Qwen_cpt_version\region_preprocessing_v2\build.py --out AI\Qwen_cpt_version\region_preprocessing_v2\runs\it3170_v2_next
```

Không dựng đè release. `make_notebook.py` sinh notebook v2 độc lập, không sửa notebook cũ. `table_integration_test.py` là kiểm thử CPU dùng model thật; thử adapter canary thành công rồi mới batch. Kết quả sửa bbox bổ sung được giữ tại `evidence/table_bbox_retry/` thay vì ghi đè lần lỗi đầu.
