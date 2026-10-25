# Bắt đầu preprocessing v6 — 134 gói độc lập

**Train CPT sau kiểm duyệt (23/10/2026):** bộ 27 học phần được xuất riêng tại [training_releases/cpt_27courses_20261023](training_releases/cpt_27courses_20261023). Xem [báo cáo lấy mẫu](training_releases/cpt_27courses_20261023/AUDIT_REPORT.md) và [hướng dẫn Colab](training_releases/cpt_27courses_20261023/HUONG_DAN_COLAB.md). Dùng cặp notebook `BKQuiz_Qwen3_1_7B_CPT_27courses.ipynb` / ZIP `bkquiz_cpt_27courses_20261023.zip` trong release này, không dùng gói IT3170 cũ. Chấp nhận mặc định dữ liệu chưa từng duyệt chỉ áp dụng cho release được chủ dữ liệu cho phép này; các quyết định reject và split bảo vệ được giữ.

**Đã triển khai lên Drive 24/10/2026:** [mở notebook Colab](https://colab.research.google.com/drive/13mMgdUsmGCukOKrCw2GxK2P1LNGiBozB), chọn GPU và chạy các cell theo thứ tự. Bản cuối có **37.133 mẫu / 3.235.037 token / 395 optimizer steps cho 1 epoch**. ZIP đã ở `MyDrive/BKQuiz_CPT` và được tải lại kiểm SHA-256; [thông tin triển khai](training_releases/cpt_27courses_20261023/OPEN_COLAB.md). Chưa thực thi train GPU trong lượt đóng gói này.

**Kiểm duyệt kết quả đã nhập ngày 23/10/2026:** 134 gói / 27 học phần / 13.314 trang được gộp tại `workspaces/unit100_v6_20261022/runs`. Mở [Start_Review.cmd](workspaces/unit100_v6_20261022/Start_Review.cmd), rồi truy cập [web kiểm duyệt](http://127.0.0.1:8765/). Trang đầu cho phép chọn học phần và mở hàng đợi VLM hoặc chế độ kiểm tra toàn bộ text/bảng/công thức. Xem [hướng dẫn và vị trí lưu quyết định](workspaces/unit100_v6_20261022/README_KIEM_DUYET.md).

**Cập nhật 23/10:** dùng [notebook JSONL Fix](colab_orchestrator_v5/Colab_V6_L4_134_Units_JSONL_Fix.ipynb) và [runtime JSONL Fix](colab_orchestrator_v5/colab_orchestrator_v5_v6_jsonl_runtime.zip) cho phiên mới. Đang chạy và gặp lỗi ở gói 61: sao chép [cell vá và tiếp tục](colab_orchestrator_v5/COLAB_JSONL_REPAIR_AND_RESUME.txt) vào một cell Colab mới sau khi cell lỗi đã dừng. Giữ cùng BASE, venv và 134 input. Xem [hướng dẫn chi tiết](colab_orchestrator_v5/JSONL_FIX_REPORT_20261023.md).

Phiên bản mặc định: **preprocessing 6.0.0 / orchestrator v5**, chạy **Python 3 / L4 / High-RAM**. Core v5.0.0 chính thức giữ nguyên; runtime mới xử lý nền ảnh lặp, giới hạn số vùng/dung lượng và thêm deadline/tiến độ.

1. Giữ nguyên 134 ZIP và index trong **MyDrive/BKQuiz_cpt_data/inputs_134**. Nếu đã upload thì không upload lại.
2. Upload [runtime JSONL Fix](colab_orchestrator_v5/colab_orchestrator_v5_v6_jsonl_runtime.zip) vào **MyDrive/BKQuiz_cpt_data**, bên ngoài inputs_134.
3. Mở [notebook JSONL Fix](colab_orchestrator_v5/Colab_V6_L4_134_Units_JSONL_Fix.ipynb) thành một tài liệu Colab riêng; dùng kernel sạch, Python 3/L4/High-RAM. Dừng SESSION cũ sau khi gói hiện tại đã lưu; không chạy hai queue cùng GPU/BASE.
4. Chạy các cell theo thứ tự. Smoke test Docling phải đạt trước queue. Cache model đang dùng nằm trong /content; Docling cache được lưu thành ZIP có hash trên Drive sau khi kiểm tra.
5. Xem [hướng dẫn vận hành](colab_orchestrator_v5/README.md), [báo cáo triển khai](colab_orchestrator_v5/REPORT.md) và [kiểm tra artifact](colab_orchestrator_v5/FINAL_VALIDATION_20261023.json).

BASE mới: **MyDrive/BKQuiz_v6_unit100**. BASE 134 gói trước **BKQuiz_v5_unit100** chỉ được đọc khi nhận lại ZIP hoàn chỉnh. Dữ liệu cũ giữ nguyên version/quality và được đánh dấu legacy; không coi là đã chạy policy v6. Muốn xử lý lại tất cả theo v6, chọn BASE khác, PREVIOUS_BASE=None và REUSE_PRECOMPLETED=False.

Mỗi gói vẫn tối đa 100 trang; **134 gói / 27 PDF / 13.314 trang**. Một batch giới hạn 20 trang, 256 request và 64 MiB asset. Nền IT4906 đã xác minh bị loại trước crop/OCR; ảnh nhỏ chưa biết không bị tự xóa. Vùng quá nhiều giữ toàn trang/audit và cần kiểm tra. Kết quả VLM vẫn qua human review, không tự xuất CPT.

Kết quả từng gói được đóng trong /content, kiểm SHA-256 khi lưu Drive rồi mới ghi receipt. Runtime mất thì chỉ chạy lại gói dở/thiếu/hỏng, giữ mọi gói hoàn chỉnh. Tải kết quả qua giao diện Drive; không files.upload/files.download và không DA_TAI.

**52/52 kiểm thử cục bộ đạt**, core giữ 48/48 hash, 134 ZIP input không dựng lại. Mốc 22/10 đã kiểm hash toàn bộ 134 ZIP; mốc 23/10 xác nhận index giữ nguyên và tái hiện/khắc phục lỗi JSONL khi native/đóng gói đúng 100 trang IT4025. Đã kiểm tra thực cấu trúc bảy trang IT4906 và loại 170.646 mảnh nền khỏi model tasks; chưa chạy GPU Colab thực tế hoặc đo lại chất lượng OCR/VLM toàn corpus. Deadline và guard không bảo đảm Colab không mất kết nối.

Các phiên bản [orchestrator v4](colab_orchestrator_v4/README.md) và [v3](colab_orchestrator_v3/README.md) được giữ. Bản entrypoint trước v6 nằm trong colab_orchestrator_v5/releases/entrypoints_before_v6_20261022.
