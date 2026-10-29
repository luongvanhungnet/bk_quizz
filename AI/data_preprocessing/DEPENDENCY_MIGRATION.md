# Chuyển phụ thuộc AI — 29/10/2026

Core mới: `AI/Qwen_cpt_version/region_preprocessing_v5_0_1`.
Môi trường Python mới: `AI/data_preprocessing/.venv/Scripts/python.exe`.
Không xóa các folder cũ; không thay ZIP/notebook đã phát hành trên Drive.

## Vị trí mới

| Dữ liệu/công cụ cần giữ | Vị trí hiện hành |
|---|---|
| Native cache từ hybrid | `AI/data_preprocessing/dependency_data/native` |
| Vùng ảnh từ region v1 | `AI/data_preprocessing/dependency_data/regions` |
| Seed và split bảo vệ từ region v3 | `AI/data_preprocessing/dependency_data/benchmark` |
| Run IT3170 dùng lại từ region v5 | `AI/data_preprocessing/dependency_data/it3170_v5` |
| Dữ liệu nguồn CPT pilot | `AI/data_preprocessing/dependency_data/pilot_cpt` |
| Fixture kiểm thử phân 134 gói | `AI/data_preprocessing/colab_orchestrator_v5/fixtures/corpus_plan` |
| Công cụ SFT native, runtime và kiểm thử | `AI/Qweun_sft_version/sft_v2_tools/completed_native` |

Manifest dữ liệu lịch sử được giữ nguyên byte và kiểm SHA-256 trong
`DEPENDENCY_MIGRATION.json`. Core 5.0.1 đổi các đường dẫn lịch sử khi đọc,
không sửa dữ liệu gốc hoặc tạo quyết định duyệt. Bản official 5.0.0 giữ nguyên.
`production.json` và config snapshot chỉ đổi đường dẫn `reuse_runs` cùng nhau.

## Các folder cũ được thay thế

- `AI/Qwen_cpt_version/data_preprocessing`
- `AI/Qwen_cpt_version/hybrid_preprocessing`
- `AI/Qwen_cpt_version/region_preprocessing`
- `AI/Qwen_cpt_version/region_preprocessing_v2`
- `AI/Qwen_cpt_version/region_preprocessing_v3`
- `AI/Qwen_cpt_version/region_preprocessing_v5`
- `AI/data_preprocessing/uploads_14_sequential_20261021`
- `AI/Qweun_sft_version/completed_sft_tools`
- `AI/Qwen_cpt_version/region_preprocessing_v5_official` (core cũ, hiện đã chọn 5.0.1)

Chỉ các phần đang cần của dữ liệu được chuyển. Kết quả thử nghiệm khác trong
folder cũ không tự được đưa vào phiên bản mới. Xóa folder cũ sẽ bỏ các hồ sơ
thử nghiệm đó. Các đường dẫn ghi trong báo cáo lịch sử và gói đã khóa vẫn có
thể nhắc tên folder cũ; đó không phải phụ thuộc chạy của mã hiện hành.

## Dựng lại input mà không cần bộ 14 gói cũ

`build_inputs.py` nhận thêm `--plan` để dùng plan đã giữ trong bộ 134 gói:

```powershell
AI/data_preprocessing/.venv/Scripts/python.exe -X utf8 AI/data_preprocessing/colab_orchestrator_v5/build_inputs.py --plan AI/data_preprocessing/uploads_134_unit100_20261022/plan/plan.json --out "D:/BKQuiz/AI/data_preprocessing/inputs_rebuilt"
```

Lệnh này tạo bộ input mới, không ghi đè bộ 134 gói đang dùng. Chỉ thực hiện
khi cần dựng lại; đợt chuyển phụ thuộc không đóng gói lại hoặc upload input.

## Kiểm chứng

Đã đạt **319 kiểm thử**: core 167, điều phối 52, web duyệt 18, SFT native 30, SFT-v2 30, so sánh model 15, registry/hash 5 và 2 kiểm tra seed/plan. Các suite chạy với cơ chế chặn đọc folder cũ; kiểm tra seed/plan còn chặn cả core official 5.0.0. Đối chiếu SHA-256 đạt cho **14,100 file dữ liệu**. Xem `MIGRATION_VALIDATION.json` và `migration_evidence/`.

Không chạy lại OCR/VLM/GPU hoặc train model trong đợt chuyển đường dẫn này.
