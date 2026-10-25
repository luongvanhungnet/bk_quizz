# Data preprocessing chính thức

Phiên bản mặc định: **v5.0.0**. `manage.py` chạy release đã chốt; `CURRENT.json` và SHA-256 bảo vệ snapshot khỏi thay đổi âm thầm. Lớp [điều phối Colab v4](colab_orchestrator_v4/README.md) đọc **134 input độc lập, tối đa 100 trang xử lý/gói** từ `MyDrive/BKQuiz_cpt_data/inputs_134`. Mỗi gói xử lý/đóng ZIP trên `/content`, lưu và kiểm hash trên Drive rồi mới ghi biên nhận. Khi chạy lại chỉ xử lý gói thiếu/hỏng; gói dở chạy lại từ đầu. Tải kết quả riêng bằng Google Drive; không dùng widget upload/download và không chờ DA_TAI. `CURRENT_ORCHESTRATOR.json` chỉ rõ notebook, runtime ZIP và bộ input hiện hành.

- [Đặc tả chính thức](SPEC_V5_OFFICIAL.md)
- [Runbook toàn corpus](RUNBOOK_CORPUS.md)
- [Bắt đầu với notebook điều phối và 134 gói upload](START_HERE.md)
- [Báo cáo chuẩn bị và trạng thái còn lại](PREPARATION_REPORT.md)
- [Kiểm kê đọc nhanh](CORPUS_INVENTORY.md)
- [Cấu hình](production.json)
- [Inventory 27 học phần](catalogs/corpus_20261021/documents.csv)
- [Kế hoạch thực thi](plans/corpus_20261021/jobs.jsonl)

Phạm vi hiện tại: **27 PDF, 13.314 trang**. Kế hoạch corpus gốc có 148 shard theo PDF; kế hoạch điều phối mới đóng thành 134 gói toàn corpus, gồm 158 phần theo PDF để giữ đúng phạm vi nguồn khi một gói đi qua ranh giới học phần. Đã chuẩn bị 7 gói/700 trang tái sử dụng từ kết quả v3 có trên máy. IT3170 giữ seed và lịch sử đã có; 26 học phần khác đi qua discovery/layout trước inference. Web human review chỉ xử lý mô tả VLM thành công.

Tại `D:\BKQuiz`:

```powershell
$py = 'AI\Qwen_cpt_version\data_preprocessing\.venv\Scripts\python.exe'
& $py -X utf8 AI\data_preprocessing\manage.py verify
& $py -X utf8 AI\data_preprocessing\manage.py preflight --plan AI\data_preprocessing\plans\corpus_20261021
```

Không suy diễn từ việc chốt phiên bản rằng toàn corpus đã sạch hoặc mọi prediction đã được xác minh. Đặc tả ghi rõ các gate source, layout, VLM review, dedup/split và CPT export.
