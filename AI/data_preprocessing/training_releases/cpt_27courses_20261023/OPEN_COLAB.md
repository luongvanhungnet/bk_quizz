# Mở bộ CPT 27 học phần

Đã triển khai lên Drive ngày **24/10/2026**, từ release dữ liệu ngày 23/10/2026.

- [Mở notebook Google Colab](https://colab.research.google.com/drive/13mMgdUsmGCukOKrCw2GxK2P1LNGiBozB).
- [Gói dữ liệu và mã train](https://drive.google.com/file/d/1isYMGOGft_OrQ_sUCtR-79HQ9ePW4mbo/view?usp=drivesdk), đã nằm đúng thư mục `MyDrive/BKQuiz_CPT`.
- [Thư mục Drive](https://drive.google.com/drive/folders/1jlG0ku6cyqvZKT4vLR9p76dabexB-LI1).

Chọn Python 3 / GPU, ưu tiên L4 nếu được cấp, rồi chạy các cell theo thứ tự. Notebook kiểm hash ZIP, tạo môi trường, tokenize, chạy smoke 2 bước, sau đó CPT 1 epoch. Bản này có **37.133 mẫu / 27 học phần / 3.235.037 token gồm EOS / 3.160 sequence**, tương ứng **395 optimizer steps** theo cấu hình mặc định.

Đầu ra: `MyDrive/BKQuiz_CPT/runs/cpt_27courses_20261023_001/train/adapter`. Mất phiên thì giữ RUN_NAME, chạy lại phần chuẩn bị và đặt `RESUME_TRAIN=True`.

ZIP đã được tải lại từ Drive và đối chiếu SHA-256 thành công: `6da7e92a75a4d9291ce23697fb9dfa1a309cf99b289f230bee50fa833919ac62`. Notebook khóa đúng hash này. Đã kiểm CPU; **chưa chạy train trên GPU/Colab** trong lượt triển khai.

Xem [báo cáo lấy mẫu](AUDIT_REPORT.md), [hướng dẫn chi tiết](HUONG_DAN_COLAB.md) và [kiểm tra dữ liệu/token](LOCAL_VALIDATION.json). Trong 24 mẫu đã đối chiếu, 6 mẫu không phù hợp và các bản trùng tương ứng được cách ly (30 vùng). Nhóm chấp nhận mặc định vẫn có rủi ro OCR/công thức, không được gắn nhãn human-verified.
