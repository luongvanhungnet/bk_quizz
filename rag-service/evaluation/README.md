# Bộ đánh giá RAG

Mỗi dataset là một mảng JSON. Trường bắt buộc: `question`, `expectedDocumentIds`; tùy chọn `expectedPageNumbers`, `documentIds`, `expectedAnswerable`.

```powershell
python -m app.cli.evaluate evaluation/datasets/my-dataset.json --user-id <UUID> --skip-generation
```

`EVALUATION_MAX_RECALL_DROP` mặc định là `0.02`. Khi đánh giá answer, citation trỏ tài liệu ngoài tập kỳ vọng cũng làm lệnh trả exit code 2.
