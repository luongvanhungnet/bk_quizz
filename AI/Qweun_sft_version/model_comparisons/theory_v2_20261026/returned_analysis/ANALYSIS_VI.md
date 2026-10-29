# Phân tích ba lượt chạy Colab SFT-v2 — 26/10/2026

Các lượt chạy đã hoàn tất, dùng đúng bộ input đã phát hành và đúng adapter vừa train.
Tuy nhiên, **pipeline hiện chưa đạt chất lượng để tạo quiz tự động**. SFT-v2 tăng nhẹ điểm
trả lời MCQ, nhưng chưa cho thấy cải thiện ở tác vụ lý thuyết → quiz có giải thích và nguồn.
Đã phát hiện lỗi xử lý Unicode/EOS trong lớp ràng buộc JSON; cần sửa và đánh giá lại checkpoint hiện có.

## 1. Kiểm chứng kết quả

Nguồn trên Drive: [schema_diag_001](https://drive.google.com/drive/folders/1bcADxAWbKIHYXYKgjJJ_E68hWqcy7dct),
[sft_v2_001](https://drive.google.com/drive/folders/1w_Nf8qOB1tXvpN9m9lm5zMtnMDjhIAWX),
[final_test_001](https://drive.google.com/drive/folders/1fM05H_Ds00i-W5ITAF_LDP7lajXKYQpT).

- Đối chiếu ba manifest input với bản phát hành `theory_v2_curated_20261025`.
- Kiểm tra SHA256 của 12 đầu ra train; checksum các file và từng record của benchmark.
- Chấm lại 160 record chẩn đoán và 200 record test bằng bộ chấm trong input đã khóa.
- Kiểm tra 200 câu trả lời trong blind review khớp nguyên văn output tương ứng.
- Base và adapter dùng cùng Tesla T4, FP16, NF4, môi trường thư viện và giao thức test.
- Adapter được đánh giá có SHA256 `7366567d26cfe4f649cc78744e4e1855b53444e327e28b82e056dd21484b7060`,
  khớp adapter vừa train. Có 392 tensor, 8.716.288 tham số, tất cả hữu hạn và LoRA B đã thay đổi.

Đây là kiểm tra tính nhất quán của artifact và phép chấm. Chưa có duyệt ngữ nghĩa bởi chuyên gia.
Giữ nguyên các file, model, số liệu cũ và dữ liệu gốc trên Drive.

## 2. Chẩn đoán bốn phiên bản cũ

| Phiên bản | MCQ raw /40 | MCQ có grammar /40 | Quiz raw, ID chính xác /12 | Quiz có grammar, ID chính xác /12 |
|---|---:|---:|---:|---:|
| Base | 20 | 21 | 0 | 3 |
| CPT | 8 | 18 | 0 | 0 |
| SFT cũ | 18 | 21 | 3 | 1 |
| CPT+SFT | 1 | 20 | 2 | 1 |

Grammar loại hết câu trả lời MCQ không hợp lệ trên 40 câu cũ cho cả bốn bản. CPT+SFT tăng
từ 1 lên 20 câu khớp đáp án: lỗi đầu ra đóng góp lớn vào mức sụt điểm trước đây. Điều này
chưa chứng minh bản đó tốt hơn Base hoặc SFT. Quiz vẫn thường sai quote, lặp phương án,
sai số đáp án và đôi khi JSON hỏng. Ép định dạng chưa giải quyết được nội dung.

40 câu/12 quiz này đã dùng phân tích lỗi, chỉ là regression/dev. Không gộp điểm với test mới.
SFT cũ có 4/12 theo validator cũ nhưng còn 3/12 khi kiểm tra source ID chính xác.

## 3. Benchmark mới: Base và SFT-v2

| Chỉ tiêu | Base | SFT-v2 |
|---|---:|---:|
| MCQ khớp khóa nguồn, closed-book | 31/100 | 35/100 |
| Quiz đọc được bằng strict JSON | 80/100 | 74/100 |
| Quiz qua riêng JSON Schema | 77/100 | 74/100 |
| Quiz giữ đáp án tham chiếu theo so khớp văn bản | 34/100 | 30/100 |
| Quiz qua toàn bộ kiểm tra tự động | 0/100 | 0/100 |
| Quiz chạm giới hạn 1.536 token khi chưa kết thúc | 0/100 | 10/100 |

**0/100 qua toàn bộ kiểm tra không có nghĩa mọi câu đều sai kiến thức.** Chỉ tiêu này gộp
cấu trúc, dữ kiện bắt buộc, chỉ số distractor, nguồn và sự khớp bản thiết kế. Một số mẫu trả lời
hợp lý vẫn trượt vì thêm nhãn vào option hoặc sửa khoảng trắng lỗi từ PDF. Tuy vậy, các lỗi
gắn nguồn và giải thích sai phương án đủ nghiêm trọng để chặn xuất quiz tự động.

MCQ chỉ nhận câu hỏi và phương án; không nhận lý thuyết. Phần sinh quiz được cấp sẵn source
cards đúng. Vì vậy, benchmark này **chưa đo chất lượng retrieval/RAG**.

SFT-v2 đúng thêm 6 câu mà Base sai và sai 2 câu Base đúng; cả hai cùng đúng 29 câu.
McNemar exact hai phía khoảng 0,289, chỉ mang tính mô tả vì các câu có chung nguồn.
Chênh lệch +4 điểm chưa đủ để kết luận cải thiện đáng tin cậy. Test có 3 học phần, 62 họ fact;
100 câu không phải 100 quan sát độc lập. 85 câu từ hai PDF chưa dùng trong SFT-v2, 15 câu từ
các nhóm trang giữ lại. CPT cũ đã thấy các PDF này.

| Học phần | Số câu | Base MCQ đúng | SFT-v2 MCQ đúng |
|---|---:|---:|---:|
| IT3100 | 38 | 14 | 15 |
| IT4060 | 15 | 4 | 4 |
| IT4788 | 47 | 13 | 16 |

## 4. Các nguyên nhân đã thấy trong đầu ra

**Lỗi Unicode/EOS trong grammar.** Phát lại nguyên token của ba mẫu hỏng trên CPU với
LMFE 0.11.3 cho thấy tất cả token đã sinh đều được filter cho phép, kể cả EOS khi JSON chưa
đóng. Trường hợp ngắn nhất dừng tại `"prompt": "Đ` rồi whitespace/EOS.

Tokenizer alphabet và parser config có `Đ`, nhưng cache `alphabet_without_quotes` được
khởi tạo trước đó không có ký tự này. Khi `minLength=1` và ký tự đầu chuỗi là `Đ`, stack
parser trở thành rỗng, làm EOS được phép. Đây là lỗi tích hợp grammar có thể tái hiện,
không phải bằng chứng riêng rằng trọng số không học. CPU replay chỉ xác nhận các đường token
đã quan sát; chưa tạo một phiên bản decoder sửa hoàn chỉnh hoặc chạy lại GPU.

Mã nguồn đối chiếu: [JsonSchemaParser](https://github.com/noamgat/lm-format-enforcer/blob/main/lmformatenforcer/jsonschemaparser.py),
[TokenEnforcer](https://github.com/noamgat/lm-format-enforcer/blob/main/lmformatenforcer/tokenenforcer.py).
Bản cài thực tế 0.11.3 được giữ tại `_deps` của công cụ. Kiểm thử trước đây xác nhận có đường
token tạo JSON tiếng Việt hợp lệ; chưa bao phủ đầy đủ chuỗi mở đầu bằng ký tự như `Đ`.

**Lỗi nội dung và liên kết vẫn tồn tại trong JSON hoàn chỉnh.** Trong 100 quiz mỗi bản
(một mẫu có thể mắc nhiều lỗi):

| Lỗi | Base | SFT-v2 |
|---|---:|---:|
| Không giải thích đúng tập phương án sai | 74 | 68 |
| Nguồn cho đáp án không khớp mục tiêu được yêu cầu | 54 | 50 |
| Nguồn giải thích distractor không đúng | 30 | 25 |
| Thiếu dữ kiện bắt buộc trong câu hỏi | 17 | 17 |
| JSON hỏng | 20 | 26 |

Mẫu phổ biến là luôn gán ba giải thích vào option `[0,1,2]` dù phương án sai thực tế khác.
Có 60 mẫu Base và 61 mẫu SFT-v2 dùng đúng bộ chỉ số này. Cần liên kết giải thích với ID
phương án ổn định và kiểm tra cả nội dung; sửa chỉ số bằng code không tự chứng minh lời giải đúng.

**Validation chưa phân biệt được checkpoint đạt yêu cầu.** Train chạy đủ 34 step, 1 epoch,
LR 2e-5, không nạp CPT. Validation loss giảm 1,0096 ở step20 xuống 0,9551 ở step34. Nhưng cả
hai checkpoint đều có 0/4 mẫu đúng đáp án tham chiếu, đúng cấu trúc hoặc qua toàn bộ proxy.
Vì các thành phần chất lượng cùng bằng 0, checkpoint34 được chọn nhờ loss thấp hơn.
Tên tiêu chí chọn checkpoint là generation quality chưa đồng nghĩa model đã đạt chất lượng.

Pipeline đã cho chạy benchmark đủ 100 mẫu dù validation thất bại. Cần bổ sung điều kiện dừng
để tránh tiêu GPU cho đánh giá đầy đủ trong trạng thái này.

**RAG demo đã truy xuất nguồn nhưng sinh nội dung lệch.** Query là “Thao tác nhập xuất”,
nguồn E1 mô tả thao tác vào/ra của hệ điều hành. Model lại hỏi về tính chất của hệ thống phân
tán và chọn “Hệ số song song của hệ thống”; lời giải không nhất quán với nguồn. Gate đã chặn
xuất quiz (`production_approved=false`, không có quiz đã hydrate). Một demo chưa đủ đánh giá
recall retrieval, nhưng cho thấy cấp nguồn chưa bảo đảm model bám đúng nguồn.

## 5. Thời gian đo được

Train runtime khoảng 17,2 phút, trong đó hai đợt generation validation chiếm khoảng 11,8 phút.
Ở benchmark mới, tổng thời gian decode ghi trong các batch khoảng 3 giờ 42 phút:

- Base: MCQ khoảng 0,9 phút; sinh quiz khoảng 73,9 phút.
- SFT-v2: MCQ khoảng 1,2 phút; sinh quiz khoảng 146,0 phút.

Đây là tổng thời gian generate đã ghi, không phải tổng thời gian từ lúc mở notebook đến khi
kết thúc. Không gồm setup, tải model, chuẩn bị grammar hay khoảng gián đoạn giữa các cell.
SFT-v2 sinh 62.679 token quiz so với 43.367 token của Base, có lặp lời giải và 10 lần chạm cap.
Chạy full benchmark trước khi validation qua gate là phần chi phí có thể tránh.

## 6. Hướng đi đề xuất

1. **Ưu tiên sửa decoder bằng checkpoint hiện có.** Thêm ca kiểm tra Unicode đầu chuỗi,
   escape, batch có độ dài khác nhau, không cho EOS trước JSON hoàn chỉnh. Đánh giá generation
   trên validation sau khi sửa; không sửa/hydrate output hỏng rồi thay điểm kết quả cũ.
2. **Đưa cấu trúc ổn định về code:** giữ ID phương án, nguồn và nội dung option từ source
   planner; model tập trung sinh câu hỏi và giải thích có căn cứ. Kiểm tra quan hệ giữa đáp án,
   từng distractor và nguồn. Phép MCQ closed-book vẫn phải tách riêng, không cấp sẵn khóa đáp án.
3. **Thêm gate trước benchmark đầy đủ:** nếu không có mẫu validation nào qua proxy hoặc
   JSON hỏng có hệ thống, dừng với báo cáo lỗi. Mở rộng validation generation từ 4 lên một tập
   khoảng 20 mẫu đa dạng được kiểm tra; ngưỡng chất lượng là tiêu chí thử nghiệm cần ghi rõ.
4. **Chỉ thiết kế lượt train tiếp sau khi pipeline đo ổn định.** Rà soát dữ liệu và lời giải,
   tập trung đa dạng nhiệm vụ và chất lượng căn cứ. Kết quả này chưa đủ lý do tăng epoch,
   đổi model lớn hơn hay quay lại CPT. Nếu dùng 100 mẫu hiện tại để tinh chỉnh prompt/train,
   chuyển chúng thành regression và giữ một test mới cho kết luận tiếp theo.

Giữ adapter SFT-v2 như artifact thử nghiệm; chưa thay model đang phục vụ. Chưa có lượt train
hoặc inference GPU mới nào được chạy trong đợt phân tích này.

Bằng chứng tại cùng thư mục: `AUDIT.json`, `case_audit.json`, `DECODER_REPLAY.json`,
`DRIVE_SOURCE_RECEIPT.json`, ba ZIP gốc, các log và script CPU để tái kiểm tra.
Theo các artifact đã hoàn tất trong dự án, **lượt CPT gần nhất là CPT27**, còn **lượt SFT gần nhất là SFT-v2 (`sft_v2_001`)**.

**Điểm cần phân biệt: SFT-v2 được train trực tiếp từ Base với LoRA mới, không train tiếp từ CPT.** Nhánh CPT+SFT trong bảng trước là một lượt cũ hơn.

| Thông số | CPT27 | SFT-v2 mới nhất |
|---|---|---|
| Model nền | Qwen/Qwen3-1.7B | Qwen/Qwen3-1.7B |
| Revision nền | `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` | Cùng revision |
| Mục tiêu | Học tiếp văn bản chuyên ngành bằng dự đoán token tiếp theo | Học sinh quiz từ lý thuyết, kèm đáp án, giải thích và nguồn |
| Khởi tạo | Base + LoRA mới | Base + LoRA mới, không nạp CPT |
| Dữ liệu train | 37.133 mẫu văn bản từ bộ 27 học phần | 270 mẫu |
| Dữ liệu validation | Không có tập độc lập trong lượt train này | 30 mẫu |
| Dữ liệu test | Không có chỉ số test trong kết quả train | 100 mẫu, tách khỏi train và chọn checkpoint |
| Dữ liệu sau đóng gói | 3.160 chuỗi, tổng 3.235.037 token gồm EOS | Dùng dữ liệu hội thoại đã tokenize |
| Độ dài chuỗi CPT | 1.024 token | — |
| Số epoch | 1 | 1 |
| Số bước cập nhật thực tế | 395 | 34 |
| Learning rate | `2 × 10⁻⁵` | `2 × 10⁻⁵` |
| Batch size trên GPU | 1 | 1 |
| Gradient accumulation | 8 | 8 |
| Batch hiệu dụng trên 1 GPU | 8 mẫu/chuỗi | 8 mẫu |
| Optimizer | AdamW (`adamw_torch`) | AdamW (`adamw_torch`) |
| Learning-rate scheduler | Cosine | Cosine |
| Warmup ratio | 3% | 3% |
| Weight decay | 0,01 | 0,01 |
| Gradient clipping | 1,0 | 1,0 |
| Gradient checkpointing | Có | Có |
| Lượng tử hóa khi nạp nền | 4-bit NF4, double quantization | 4-bit NF4, double quantization |
| Seed | 42 | 42 |
| Thời gian train do Trainer ghi | 2.064,92 giây ≈ **34,4 phút** | 1.030,00 giây ≈ **17,2 phút** |

Hai lượt dùng cấu hình LoRA giống nhau:

| Thông số LoRA | Giá trị |
|---|---|
| Rank `r` | 8 |
| Alpha | 16 |
| Dropout | 0,05 |
| Bias | Không train |
| Module áp dụng | `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` |
| Số tham số trainable | 8.716.288 |

Kết quả ghi nhận:

| Chỉ tiêu | CPT27 | SFT-v2 |
|---|---:|---:|
| Train loss trung bình | 1,9416 | 1,0792 |
| Loss trên 64 chuỗi train cố định, trước → sau CPT | 1,7366 → 1,5073 | — |
| Validation loss cuối | Không có | 0,9551 |
| Checkpoint được xuất/chọn | Kết thúc tại step 395 | Step 34 |
| Kiểm tra sinh trên validation | Không có trong log train này | Cả step 20 và 34 đều đạt **0/4** ở các tiêu chí chất lượng nêu trong báo cáo |

**Không nên so trực tiếp train loss 1,9416 và 1,0792 để kết luận SFT tốt hơn CPT**, vì hai lượt học dữ liệu và mục tiêu khác nhau. Loss chẩn đoán CPT cũng được đo trên dữ liệu train, nên chưa chứng minh khả năng tổng quát hóa.

Với SFT-v2, checkpoint 34 được chọn nhờ validation loss thấp hơn khi các thành phần chất lượng sinh đều bằng 0. Benchmark sau train đạt **35/100 MCQ**, nhưng **0/100 quiz qua toàn bộ kiểm tra tự động**; adapter vẫn là bản thử nghiệm, chưa được duyệt để phục vụ.

Nguồn đối chiếu: [cấu hình CPT](D:/BKQuiz/AI/data_preprocessing/training_releases/cpt_27courses_20261023/colab/config.json), [kết quả CPT](D:/BKQuiz/AI/data_preprocessing/training_evaluations/cpt_27courses_20261023_001/extracted/cpt_27courses_20261023_001/train/completed.json), [mã cấu hình train SFT-v2](D:/BKQuiz/AI/Qweun_sft_version/sft_v2_releases/theory_v2_curated_20261025/training_input/runtime/train_v2.py), [báo cáo SFT-v2](D:/BKQuiz/AI/Qweun_sft_version/model_comparisons/theory_v2_20261026/returned_analysis/ANALYSIS_VI.md).