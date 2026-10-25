# Kết quả thử kiến trúc tiền xử lý local + Colab

Ngày: 2026-10-18. Tài liệu: IT3170 — Thuật toán ứng dụng, **1.060 trang**. SHA-256 nguồn: `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`.

**Phần Windows đã chạy thật. Phần Colab đã chuẩn bị notebook và gói đầu vào, chưa chạy inference GPU trong phiên này. Chưa thể kết luận toàn bộ kiến trúc đạt chất lượng nội dung.** Không dùng kết quả CPU Paddle cũ để báo thành kết quả Colab mới.

## Phần đã đo trên máy hiện tại

Máy: Intel i7-1165G7, RAM 8 GB. Trích xuất lại từ PDF, render rộng 1.400 pixel, giữ ánh xạ trang nguồn trong manifest trước đó. Môi trường Python local tái sử dụng `data_preprocessing/.venv`; không cài GPU model mới trên Windows.

| Công việc | Kết quả |
|---|---|
| Đọc PDF, lấy chữ theo tọa độ và render | Đủ 1.060/1.060 trang |
| Thời gian đọc/render xấp xỉ | 90,0 giây; lấy chênh lệch timestamp ghi document.json và native_pages.jsonl, không phải profiler từng hàm |
| Làm sạch | NFC, giữ số/dấu/code, nối dòng theo block, lọc lề/số trang và che PII có nhãn |
| Trạng thái qua cổng native sơ bộ | 326 trang |
| Trạng thái cần rà soát | 734 trang |
| SHA-256 chữ | 63 nhóm có cùng văn bản sau làm sạch |
| SHA-256 cả chữ và ảnh trang | 9 trang có bản trùng toàn trang trong toàn tài liệu |
| MinHash + SimHash | 737 cặp ứng viên gần trùng; giữ nội dung, không tự xóa |
| Thời gian dedup | 1,22 giây |
| Đóng gói preview | 326 mẫu, 33.925 token gồm EOS, 34 sequence tối đa 1.024 token |
| Thời gian tokenize/packing | 20,26 giây, gồm nạp tokenizer lần đầu |
| Làm sạch + dedup + packing + tạo gói Colab | 24,03 giây; không gồm bước đọc/render đã chạy riêng |
| GPU OCR/formula/VLM | Chưa chạy, không có số thời gian hoặc độ chính xác thực tế |

Các thời gian chỉ thuộc lượt chạy này. Không có số đo RSS đỉnh; không suy ra yêu cầu RAM đỉnh từ RAM lắp trên máy.

9 trường hợp trùng cả chữ/ảnh nằm trong tập toàn tài liệu; không nằm trong tập 326 trang qua cổng native, nên bản preview vẫn có 326 mẫu. Không lấy 63 nhóm trùng chữ để tự xóa slide: hai trang có thể cùng nhãn nhưng khác đồ thị. Native accepted chỉ là cổng sơ bộ; layout bằng model và các hình/công thức còn chưa được kiểm tra ở đợt này. Bản preview ghi **training_ready=false**, không thay bộ train đã làm sạch trước đây.

## Ba thuật toán khử trùng

- SHA-256: hash văn bản sạch để báo nhóm; chỉ bỏ bản dư khi cả chữ và hash ảnh trang nguyên vẹn đều giống nhau. Giữ metadata tất cả trang nguồn trong normalized.
- MinHash: 128 permutations, seed 42; shingles 5 token giữ số, chữ hoa/thường, dấu toán và dấu câu; LSH đề xuất cặp rồi tính Jaccard thật, ngưỡng 0,8.
- SimHash: 64 bit; chia 4 band 16 bit để tạo ứng viên độc lập với MinHash, xác nhận Hamming ≤3. Chỉ xét text dài ít nhất 80 ký tự cho near-duplicate; SHA vẫn kiểm tra trang ngắn.
- Hợp các ứng viên MinHash/SimHash và giữ mọi cặp gần trùng để cùng split. Trước khi train chạy lại trên transcript đã xác minh sau Colab.

Chính sách giữ cả ảnh làm exact dedup bảo thủ: các trang chỉ khác số trang có thể vẫn được giữ. Ưu tiên không mất hình/kiến thức hơn việc xóa hết mọi bản trùng ngữ nghĩa.

## Phần Colab được thiết lập

| Tác vụ | Cấu hình |
|---|---|
| OCR | PaddleOCR 3.7.0, Paddle GPU 3.2.2 CUDA 11.8, PP-OCRv3 `lang=vi`, audit bảng ký tự thực tế |
| Định vị công thức | PP-DocLayout-M, bỏ ứng viên chồng lên mã native |
| Formula recognition | PP-FormulaNet-S; lưu LaTeX ứng viên, crop, hash, bbox, semantic_description=null, semantic_verified=false |
| VLM | Qwen/Qwen2.5-VL-3B-Instruct, revision `66285546d2b821cf421d4f5eb2576359d3770cd3` |
| Torch/VLM runtime | Torch 2.6.0 CUDA 12.4, Transformers 4.57.6, FP16, SDPA, batch 1 |
| Giới hạn ảnh/đầu ra | Tối đa 1.280 visual token, 1.536 token sinh; đánh dấu output có thể bị cắt |
| Lưu kết quả | Drive, từng trang; nguyên văn output, lỗi, thời gian, runtime, prompt/model/image hash |

Hai subprocess và hai venv riêng giúp tránh giữ đồng thời Paddle và Torch trên GPU. T4 16 GB là cấu hình mục tiêu thử, chưa được xác nhận VRAM đỉnh hay tốc độ tại đây. Đã kiểm tra sự tồn tại wheel Paddle GPU 3.2.2 cp312 Linux trong index CUDA 11.8 chính thức; chưa kiểm chứng cài đặt/inference trên runtime Colab thực tế.

12 trang gửi Colab: **20,49,51,129,130,300,500,800,869,1000,1042,1060**. Chọn chủ đích để thử chữ, toán, bảng, sơ đồ và vector; chưa đại diện thống kê cho 1.060 trang. Đã xem ảnh nguồn các trang 20,49,129,300,869,1042 để xác nhận nhóm có nội dung cần kiểm tra. Prompt VLM chỉ yêu cầu quan sát, không giải bài hoặc tự sửa giáo trình.

Điểm thiếu của cấu hình hiện tại: chưa có table structure recognition riêng; bảng lấy từ VLM phải đối chiếu hàng/cột. Chưa có bộ gold độc lập, nên CER/WER, Formula Accuracy, Diagram Fact Precision và Information Coverage chưa được đo. LaTeX đúng cú pháp cũng chưa chứng minh công thức đúng.

## Kiểm định đã thực hiện

- 5 kiểm thử hành vi đều PASS: cùng chữ/khác hình không bị xóa; số thay đổi được giữ; SimHash phát hiện độc lập khi MinHash không trả ứng viên; từ chối ZIP sai manifest; không xuất ứng viên VLM chưa duyệt vào train.
- Kiểm tra cú pháp Python và compile mọi code cell notebook: PASS. Đây không phải bằng chứng các thư viện GPU đã chạy thành công.
- Kiểm tra gói ZIP, manifest, hash worker/prompt và 12 ảnh đầu vào: PASS.
- Kiểm tra toàn bộ token sau packing trùng token nguồn + EOS; nhãn causal và đoạn cuối được giữ: PASS.
- Kiểm tra PDF nguồn khớp SHA-256 và manifest nguồn: PASS.

## Đầu ra và bước còn lại

- [Notebook Colab](IT3170_Hybrid_Preprocessing.ipynb).
- [Gói đầu vào Colab](runs/it3170_test/colab_input.zip), khoảng 1,7 MB.
- [Kết quả local chi tiết](runs/it3170_test/local_result.json).
- [Preview đóng gói](runs/it3170_test/local_preview.zip), chưa phải dữ liệu hoàn chỉnh để train.
- [Các nhóm trùng](runs/it3170_test/deduplication.json).
- [Hướng dẫn chạy và nhập kết quả](README.md).

Cần chạy notebook trên Colab GPU, nhận ZIP kết quả và đối chiếu nội dung. Sau khi có transcript đã xác minh, lệnh merge sẽ chạy lại dedup và tạo `reviewed_cpt/`. Chưa có bước nào tự đánh dấu mô tả VLM là kiến thức đúng.

Tài liệu đối chiếu: [PaddleOCR](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html), [Formula recognition](https://www.paddleocr.ai/main/en/version3.x/module_usage/formula_recognition.html), [Qwen2.5-VL-3B](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct).
