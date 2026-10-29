# Chuyển JSONL/CSV thành XLSX

Công cụ Python ở thư mục gốc: `D:\BKQuiz\convert_to_xlsx.py`. Cần Python 3.10 trở lên.

## Cài thư viện

```powershell
python -m pip install -r D:\BKQuiz\requirements-xlsx.txt
```

## Cách chạy

Chạy từ bất kỳ thư mục nào của terminal:

```powershell
python D:\BKQuiz\convert_to_xlsx.py "D:\du_lieu\train.samples.jsonl"
python D:\BKQuiz\convert_to_xlsx.py "D:\du_lieu\bang.csv"
```

Output mặc định là `train.samples.xlsx` hoặc `bang.xlsx`, **ngay trong thư mục hiện tại của terminal**, không phụ thuộc vị trí script/input.

Ví dụ chạy với bộ SFT-v2 hiện có:

```powershell
python D:\BKQuiz\convert_to_xlsx.py "D:\BKQuiz\AI\Qweun_sft_version\datasets\theory_sft_v2_20261025\train.samples.jsonl"
```

Tùy chọn:

```powershell
python D:\BKQuiz\convert_to_xlsx.py "D:\du_lieu\bang.csv" -o ket_qua.xlsx
python D:\BKQuiz\convert_to_xlsx.py "D:\du_lieu\bang.csv" --delimiter ";"
python D:\BKQuiz\convert_to_xlsx.py "D:\du_lieu\bang.csv" --delimiter "\t"
python D:\BKQuiz\convert_to_xlsx.py "D:\du_lieu\bang.csv" --encoding cp1258
python D:\BKQuiz\convert_to_xlsx.py "D:\du_lieu\bang.csv" --force
python D:\BKQuiz\convert_to_xlsx.py --help
```

## Cách chuyển dữ liệu

- Một bản ghi JSONL hoặc một dòng dữ liệu CSV thành một hàng. Bỏ qua dòng trống. CSV dùng hàng đầu tiên làm tiêu đề; tự nhận diện dấu phẩy, chấm phẩy, tab hoặc `|`.
- Object lồng nhau thành cột như `reference.prompt`; mảng object thành `reference.options[0].text`, `evidence[0].text`... Mảng giá trị đơn như số token được giữ dưới dạng chuỗi JSON trong một ô, tránh tạo hàng nghìn cột.
- Khóa JSON chứa dấu chấm/ký tự đặc biệt dùng ký hiệu ngoặc, ví dụ `["a.b"]`, để phân biệt với object lồng `a.b`.
- CSV giữ các giá trị ở dạng văn bản vì CSV không khai báo kiểu. Giữ được mã `00123`; không tự đoán ngày tháng hay đổi dấu thập phân.
- JSON giữ boolean và số phù hợp làm kiểu Excel tương ứng. Số nguyên dài hơn 15 chữ số, số thập phân quá chính xác/quá lớn/quá nhỏ được lưu dạng chữ để tránh làm tròn mất dữ liệu. `null` hoặc trường vắng mặt hiện thành ô trống.
- Nội dung bắt đầu bằng `=` được giữ là chữ, không biến thành công thức Excel.
- Xuống dòng CRLF/CR trong ô được chuẩn hóa thành LF để Excel hiển thị đúng, tránh nhân đôi dòng trên Windows.
- Văn bản vượt 32.767 đơn vị UTF-16 được chia tiếp sang cột `[part 2]`, `[part 3]`... Ghép các phần theo thứ tự sẽ được đầy đủ nội dung sau chuẩn hóa xuống dòng, không cắt bỏ nội dung.
- Khi vượt 1.048.575 hàng dữ liệu, tự chuyển sang `Data_2`, `Data_3`... với cùng tiêu đề. Vượt 16.384 cột sau làm phẳng thì báo lỗi.
- File có cố định hàng tiêu đề, bộ lọc, xuống dòng trong ô và độ rộng cột tối đa 72. Có thể dùng AutoFit Row Height trong Excel hoặc thanh công thức để đọc nội dung dài.
- CSV có tên cột trống/trùng được đặt tên duy nhất; CSV sai số ô hoặc JSONL lỗi báo dòng lỗi. Không âm thầm bỏ bản ghi hỏng. JSON trùng khóa, NaN/Infinity và ký tự không thể biểu diễn trong XML của XLSX bị từ chối.

Công cụ đọc hai lượt để lấy đủ cột rồi ghi workbook theo luồng, không nạp toàn bộ file vào RAM. Không sửa input. Output đã có chỉ được ghi đè khi dùng `--force`. Bản ghi lỗi làm lệnh trả mã thoát 2; không xuất workbook thiếu dữ liệu.
