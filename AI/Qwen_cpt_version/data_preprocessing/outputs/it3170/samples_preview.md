# Ví dụ dữ liệu CPT đã xuất

Các bản ghi có đầy đủ nguồn trang trong train.metadata.jsonl.

## Trang 20

Lời giải ví dụ

Khi a = b = 10^{18}, kết quả phải là 2 × 10^{18}
Giá trị này quá lớn với biến nguyên 32-bit, nên bị tràn số
Sử dụng biến nguyên 64-bit sẽ cho lời giải đúng

Nguồn: `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`, trang `20`.

## Trang 49

Bài toán: Gõ SMS

Bài toán giả thiết rằng các phím được sắp xếp như sau.

<table><tbody><tr><td></td><td>abc</td><td>def</td></tr><tr><td>ghi</td><td>jkl</td><td>mno</td></tr><tr><td>pqrs</td><td>tuv</td><td>wxyz</td></tr><tr><td></td><td>&lt;SP&gt;</td><td></td></tr></tbody></table>

Trong bảng trên mỗi ô biểu diễn một phím. <SP> biểu diễn phím space. Để hiển thị ký tự ‘a’ thì sẽ phải bấm phím tương ứng 1 lần, nhưng để hiển thị ký tự ‘b’ của cùng phím đó thì sẽ phải bấm liên tục 2 lần và đối với phím ‘c’ là 3 lần. Tương tự, bấm 1 lần cho ‘d’, hai lần cho ‘e’ và 3 lần cho ‘f’. Các ký tự khác cũng được làm tương tự. Lưu ý là để ra 1 khoảng trống thì cần bấm 1 lần phím space.

Nguồn: `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`, trang `49`.

## Trang 51

Bài toán: Gõ SMS

<table><thead><tr><th>Ví dụ dữ liệu vào</th><th>Ví dụ kết quả ra</th></tr></thead><tbody><tr><td><pre>2
welcome to ulab
good luck and have fun</pre></td><td><pre>Case #1: 29
Case #2: 41</pre></td></tr></tbody></table>

Nguồn: `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`, trang `51`.

## Trang 100

Các mô hình giải bài căn bản

Các phương pháp căn bản xây dựng lời giải bài toán

Duyệt toàn bộ

Chia để trị

Qui hoạch động

Tham lam

Mỗi mô hình ứng dụng cho nhiều loại bài toán khác nhau

Nguồn: `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`, trang `100`.

## Trang 300

Các loại cạnh

Không có trọng số hoặc Có trọng số
Vô hướng hoặc Có hướng
Trong trường hợp đồ thị có hướng, cạnh có hướng thường được gọi là cung chỉ tính định hướng của cung giữa hai đỉnh đầu mút

Sơ đồ: các đỉnh 1, 2, 3, 4; các cung 1 → 2, 3 → 1, 2 → 3, 3 → 2, 3 → 4.

Nguồn: `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`, trang `300`.

## Trang 500

Demo thuật toán Kruskal

Đồ thị vô hướng có trọng số, các đỉnh a, b, c, d, e, f, g.
Các cạnh: a—b: 7, a—d: 5, b—c: 8, b—d: 9, b—e: 7, c—e: 5, d—e: 15, d—f: 6, e—f: 8, e—g: 9, f—g: 11.
Các cạnh tô đỏ: a—b: 7, a—d: 5, b—e: 7, c—e: 5, d—f: 6, e—g: 9.

Nguồn: `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`, trang `500`.

## Trang 800

KNIGHT

```cpp
int main(){
    cin >> N >> I >> J;
    for(int i = 1; i <= N; i++)
        for(int j = 1; j <= N; j++)
            mark[i][j] = false;
    Xi[1] = I; Xj[1] = J;// starting cell
    mark[I][J] = true;
    found = false;
    cnt = 0;
    TRY(2);
    cout << cnt;
}
```

Nguồn: `c6c829f14bf2a8a1e42b6919d729fdf23865ef4734eb25817f183103dd877087`, trang `800`.
