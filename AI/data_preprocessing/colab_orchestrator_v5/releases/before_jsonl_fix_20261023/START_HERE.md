# Bắt đầu preprocessing v6 — 134 gói độc lập

Phiên bản mặc định: **preprocessing 6.0.0 / orchestrator v5**, chạy **Python 3 / L4 / High-RAM**. Core v5.0.0 chính thức giữ nguyên; runtime mới xử lý nền ảnh lặp, giới hạn số vùng/dung lượng và thêm deadline/tiến độ.

1. Giữ nguyên 134 ZIP và index trong **MyDrive/BKQuiz_cpt_data/inputs_134**. Nếu đã upload thì không upload lại.
2. Upload [runtime v6](colab_orchestrator_v5/colab_orchestrator_v5_v6_runtime.zip) vào **MyDrive/BKQuiz_cpt_data**, bên ngoài inputs_134.
3. Mở [notebook v6](colab_orchestrator_v5/Colab_V6_L4_134_Units.ipynb) thành một tài liệu Colab riêng; dùng kernel sạch, Python 3/L4/High-RAM. Dừng SESSION cũ sau khi gói hiện tại đã lưu; không chạy hai queue cùng GPU/BASE.
4. Chạy các cell theo thứ tự. Smoke test Docling phải đạt trước queue. Cache model đang dùng nằm trong /content; Docling cache được lưu thành ZIP có hash trên Drive sau khi kiểm tra.
5. Xem [hướng dẫn vận hành](colab_orchestrator_v5/README.md), [báo cáo triển khai](colab_orchestrator_v5/REPORT.md) và [kiểm tra artifact](colab_orchestrator_v5/FINAL_VALIDATION_20261022.json).

BASE mới: **MyDrive/BKQuiz_v6_unit100**. BASE 134 gói trước **BKQuiz_v5_unit100** chỉ được đọc khi nhận lại ZIP hoàn chỉnh. Dữ liệu cũ giữ nguyên version/quality và được đánh dấu legacy; không coi là đã chạy policy v6. Muốn xử lý lại tất cả theo v6, chọn BASE khác, PREVIOUS_BASE=None và REUSE_PRECOMPLETED=False.

Mỗi gói vẫn tối đa 100 trang; **134 gói / 27 PDF / 13.314 trang**. Một batch giới hạn 20 trang, 256 request và 64 MiB asset. Nền IT4906 đã xác minh bị loại trước crop/OCR; ảnh nhỏ chưa biết không bị tự xóa. Vùng quá nhiều giữ toàn trang/audit và cần kiểm tra. Kết quả VLM vẫn qua human review, không tự xuất CPT.

Kết quả từng gói được đóng trong /content, kiểm SHA-256 khi lưu Drive rồi mới ghi receipt. Runtime mất thì chỉ chạy lại gói dở/thiếu/hỏng, giữ mọi gói hoàn chỉnh. Tải kết quả qua giao diện Drive; không files.upload/files.download và không DA_TAI.

**30/30 kiểm thử cục bộ đạt**, core giữ 48/48 hash, 134 ZIP input khớp index cũ. Đã kiểm tra thực cấu trúc bảy trang IT4906 và loại 170.646 mảnh nền khỏi model tasks; chưa chạy GPU Colab thực tế hoặc đo lại chất lượng OCR/VLM toàn corpus. Deadline và guard không bảo đảm Colab không mất kết nối.

Các phiên bản [orchestrator v4](colab_orchestrator_v4/README.md) và [v3](colab_orchestrator_v3/README.md) được giữ. Bản entrypoint trước v6 nằm trong colab_orchestrator_v5/releases/entrypoints_before_v6_20261022.