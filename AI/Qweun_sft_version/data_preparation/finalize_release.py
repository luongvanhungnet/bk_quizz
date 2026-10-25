"""Document and hash a prepared SFT release, then package only validated outputs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

from scan_sources import dump


def sha(path: Path) -> str:
    with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def model_provenance(workspace: Path) -> dict:
    runtime=workspace/"AI/data_preprocessing/local_review_tools/training_runtime/config.json"
    config=read(runtime)
    adapter=workspace/"AI/data_preprocessing/training_evaluations/cpt_27courses_20261023_001/extracted/cpt_27courses_20261023_001/train/adapter"
    files={name:sha(adapter/name) for name in ["adapter_config.json","adapter_model.safetensors"] if (adapter/name).exists()}
    return {"base_model":config["model_id"],"base_revision":config["revision"],
            "current_cpt_run":"cpt_27courses_20261023_001","current_cpt_adapter_path":str(adapter),
            "current_cpt_adapter_sha256":files,"tokenizer":"Qwen3 native chat template, enable_thinking=False",
            "loss_policy":"assistant response content and im_end only; prompt/empty think block/padding masked with -100",
            "weights_loaded_or_training_started":False,
            "continuation_note":"Continue SFT from the 27-course CPT adapter (merge into the pinned base then attach a new SFT adapter, or use an equivalent verified continuation). The older local merged_hf_fp16 folder is the IT3170 pilot, not this 27-course run.",
            "cpt_independent_task_gain":"not measured; see existing training audit"}


def manifest(root: Path, workspace: Path) -> None:
    build=read(root/"build_report.json");inventory=read(root/"inventory_summary.json")
    extraction=read(root/"question_extraction_report.json");core=read(root/"rationale_core/build_report.json")
    with (root/"inventory.jsonl").open(encoding="utf-8") as stream:
        inventory_rows=[json.loads(line) for line in stream if line.strip()]
    integrity=[]
    for source in inventory_rows:
        path=Path(source["path"])
        actual=sha(path)
        if actual!=source["sha256"]:raise ValueError("Original source changed: "+str(path))
        integrity.append({"source_id":source["source_id"],"sha256":actual,"unchanged":True})
    dump(root/"source_integrity_report.json",{"files_checked":len(integrity),"passed":True,"sources":integrity})
    dump(root/"MODEL_PROVENANCE.json",model_provenance(workspace))
    main_counts=", ".join(f"{name}: {build['splits'][name]['examples']}" for name in ["train","validation","test"])
    core_counts=", ".join(f"{name}: {core['splits'][name]['examples']}" for name in ["train","validation","test"])
    rationale_counts="; ".join(f"{name}: {count}" for name,count in build["rationale_origins"].items())
    card=f"""# BKQuiz SFT từ ngân hàng đề thi - 24/10/2026

## Kết quả

- Nguồn: `{inventory['source_root']}`; {inventory['files']} PDF, {inventory['pages']:,} trang, {len(inventory['courses'])} nhóm tên môn.
- Đã đọc native {inventory['statuses'].get('extracted',0)} tệp; {inventory['statuses'].get('extraction_timeout',0)} tệp trang cuộn rất dài hết thời gian trích xuất, giữ trong hàng đợi.
- {inventory['low_text_pages']:,} trang native có dưới 80 ký tự không trắng: cần OCR/đối chiếu, chưa dùng làm nhãn SFT.
- {extraction['records']:,} đoạn câu hỏi có parser hỗ trợ; {extraction['statuses'].get('quarantine',0)} được cách ly. Những trang khác có trong `pages_review_queue.jsonl`.
- Sau lọc và khử trùng: **{build['unique_examples']} mẫu**, **{len(build['courses'])} nhóm môn**. {main_counts}.
- Tập `rationale_core/`: **{core['unique_examples']} mẫu có giải thích**, {core_counts}. Dùng cho pilot về định dạng, dẫn nguồn và giải thích; lượng dữ liệu còn nhỏ.
- `document_holdout/` giữ một cách chia toàn tài liệu độc lập để đánh giá ngoài tài liệu. Không trộn train của cách chia này với test của cách chia khác.

## Mục tiêu và giới hạn

Model được xác định từ dự án là **Qwen3 1.7B**, tiếp nối CPT 27 môn; xem `MODEL_PROVENANCE.json` để đối chiếu adapter và revision. Chưa huấn luyện, tải model hay thay model đang phục vụ.

Một mẫu gồm ngữ cảnh Q&A tham chiếu đã dẫn trang nguồn và đầu ra quiz JSON tương thích `GroundedQuizOutput` của BKQuiz. Ngữ cảnh được dựng từ câu hỏi và đáp án có sẵn, không chứa các lựa chọn nhiễu gốc. Đây là tác vụ biên soạn/chuẩn hóa ngân hàng Q&A thành quiz theo ngữ cảnh; **chưa phải tập lý thuyết -> câu hỏi hoàn toàn mới**. Không dùng điểm trên tập này để khẳng định năng lực sáng tạo câu hỏi mới từ giáo trình.

Nguồn lời giải: {rationale_counts}. Phần `source_answer_attribution` chỉ diễn đạt lại khóa đáp án và dẫn nguồn, **không phải lời giải sư phạm chi tiết**. Giải thích do Codex viết được gắn cờ riêng; nội dung dẫn nguồn phái sinh cũng chứa giải thích đó để việc học vẫn dựa trên ngữ cảnh. `human_verified=false`, `expert_semantically_verified=false` được giữ rõ ràng.

Đã phát hiện và loại các lỗi kiến thức rõ ràng trong khóa đáp án gốc (xem audit). Phần còn lại là dữ liệu có đáp án nguồn và kiểm tra cấu trúc, **chưa được chuyên gia xác minh toàn bộ**. Tập đầy đủ thích hợp làm tập ứng viên/pilot; cần rà soát thêm kiến thức trước một lượt train quan trọng. Không tự sửa nhãn hoặc gắn cờ phê duyệt của người dùng.

## Phân chia và rò rỉ

Cách chia mặc định phân tầng theo môn và theo họ câu hỏi: khử trùng chính xác sau chuẩn hóa, nhóm cùng stem, biến thể số liệu và câu gần giống trước chia. `{build['question_families']}` họ câu hỏi; `{build['family_near_pairs']}` cặp gần giống đã nhóm. Không cắt ngẫu nhiên các dòng của tập đã có. Các PDF nguồn có thể xuất hiện ở nhiều split; họ câu hỏi và nội dung trùng không được xuất hiện ở nhiều split. Đây là đánh giá trong miền, không phải đánh giá tài liệu chưa thấy.

`document_holdout/` dùng PDF và thành phần liên thông câu trùng làm đơn vị chia, nên loại hẳn dùng chung PDF giữa train/validation/test. Do nguồn có đáp án phân bố không đều, bộ này lệch môn; số liệu chi tiết ở `document_holdout/build_report.json`.

## Tệp chính

| Tệp | Ý nghĩa |
|---|---|
| `train.messages.jsonl`, `validation.messages.jsonl`, `test.messages.jsonl` | Chat gồm system, user, assistant; mỗi mẫu đúng một dòng JSON UTF-8 |
| `*.metadata.jsonl` | ID, học phần, trang, vùng hình, SHA-256 PDF, nguồn đáp án, nguồn lời giải, nhóm split |
| `tokenized/*.jsonl` | input_ids, attention_mask, labels đã mask assistant-only; không cắt mẫu dài |
| `rationale_core/` | Tập nhỏ có giải thích nguồn hoặc Codex viết có căn cứ; giữ split của tập chính |
| `questions_selected.jsonl` | Câu hỏi sạch cấu trúc trước khi dựng messages, đầy đủ dấu vết nguồn |
| `questions_quarantine.jsonl`, `release_excluded.jsonl` | Câu bị cách ly và lý do; không đưa vào train |
| `pages_review_queue.jsonl`, `source_coverage.jsonl` | Trang cần OCR/đáp án/đối chiếu; phạm vi đã thử cho mọi PDF |
| `audit/` | Lấy mẫu rủi ro, ảnh đối chiếu, phát hiện nhãn sai, lời giải có gắn xuất xứ |
| `release_manifest.json`, `validation_report.json` | Hash tệp và kiểm định cấu trúc/token/nguồn; không chứng minh toàn bộ nhãn đúng kiến thức |

Các trích xuất native đầy đủ nằm tại `extracted/` trên máy, không được chép vào ZIP train để giảm dung lượng. PDF gốc giữ nguyên. ZIP không có trọng số model hoặc tài liệu PDF gốc.

## Tái tạo và kiểm tra

Dùng Python đã có: `D:/BKQuiz/AI/Qwen_cpt_version/data_preprocessing/.venv/Scripts/python.exe`. Trong `D:/BKQuiz`:

```powershell
$py = 'AI/Qwen_cpt_version/data_preprocessing/.venv/Scripts/python.exe'
$data = 'AI/Qweun_sft_version/datasets/sft_exams_20261024'
$tools = 'AI/Qweun_sft_version/data_preparation'
$tokenizer = 'AI/data_preprocessing/training_releases/cpt_27courses_20261023/tokenizer_pinned'
& $py -X utf8 -m unittest discover -s $tools -p 'test_*.py' -v
& $py -X utf8 $tools/prepare_sft.py --dataset $data --tokenizer $tokenizer --max-length 4096 --allow-shared-source-documents
& $py -X utf8 $tools/validate_release.py --dataset $data --tokenizer $tokenizer --verify-sources --allow-shared-source-documents
```

Muốn xử lý lại nguồn: chạy `scan_sources.py --source 'D:/bk_quizz_data/đề thi' --out $data`, rồi `extract_questions.py --dataset $data` và `build_release.py --dataset $data`. Các quyết định loại cụ thể và giải thích có căn cứ được nạp lại từ audit. Nếu đã sửa code/dữ liệu, chạy lại bước tokenizer và tạo manifest trước validation; không tự sửa manifest để che lỗi. Thư mục `tools/` trong ZIP là snapshot mã tương ứng.

Không dùng runtime CPT cũ đọc trường `text` để train các tệp `messages`. Dùng `tokenized/` với collator bảo toàn labels=-100; không ghi đè labels bằng input_ids, không mask EOS theo token ID, không nối các split hay cắt/trộn lại từng dòng. Nếu dùng trainer khác, cần tái kiểm tra chat template, thinking và mask.
"""
    (root/"DATASET_CARD.md").write_text(card,encoding="utf-8")
    (root/"README.md").write_text(f"# Dữ liệu SFT BKQuiz\n\n{build['unique_examples']} mẫu từ {len(build['courses'])} nhóm môn; {main_counts}.\n\nBắt đầu đọc DATASET_CARD.md. Pilot có giải thích ở rationale_core/ ({core['unique_examples']} mẫu; {core_counts}). Tập đầy đủ còn nhiều giải thích dẫn đáp án ngắn và nhãn nguồn chưa được xác minh chuyên gia toàn bộ.\n\nModel đích: Qwen3 1.7B tiếp nối CPT 27 môn. Chưa chạy SFT. Kết quả kỹ thuật ở validation_report.json; nguồn và khóa đáp án sai đã phát hiện ở audit/.\n",encoding="utf-8")
    tools_dir=root/"tools";tools_dir.mkdir(exist_ok=True)
    for path in Path(__file__).parent.glob("*.py"):shutil.copy2(path,tools_dir/path.name)
    for name in ["document_holdout","rationale_core"]:
        preset=root/name
        paths=[p for p in preset.rglob("*") if p.is_file() and p.name not in ["release_manifest.json","validation_report.json"]]
        dump(preset/"release_manifest.json",{"schema":"bkquiz-sft-release-v1","date":"2026-10-24",
                                            "files_sha256":{p.relative_to(preset).as_posix():sha(p) for p in sorted(paths)}})
    filenames=[]
    for path in root.rglob("*"):
        if not path.is_file():continue
        relative=path.relative_to(root)
        if relative.parts[0] in ["extracted","logs","__pycache__"]:continue
        if path==root/"release_manifest.json" or path.name in ["validation_report.json","bundle_info.json"] or path.suffix==".zip":continue
        if "__pycache__" in relative.parts:continue
        if path.suffix not in [".json",".jsonl",".md",".txt",".py",".png",".svg",".log"]:continue
        filenames.append(relative.as_posix())
    dump(root/"release_manifest.json",{"schema":"bkquiz-sft-release-v1","date":"2026-10-24",
                                       "created_utc":datetime.now(timezone.utc).isoformat(),
                                       "files_sha256":{name:sha(root/name) for name in sorted(filenames)},
                                       "original_sources_embedded":False,"model_weights_embedded":False})
    print(json.dumps({"manifest_files":len(filenames),"examples":build['unique_examples'],"core_examples":core['unique_examples']},ensure_ascii=False))


def package(root: Path) -> None:
    validation=read(root/"validation_report.json")
    if validation.get("errors") or not validation.get("passed",validation.get("status")=="passed"):
        raise ValueError("Release has no successful current validation_report.json")
    if validation.get("release_manifest_sha256")!=sha(root/"release_manifest.json"):
        raise ValueError("Validation does not match the current release manifest")
    for name in ["document_holdout","rationale_core"]:
        check=read(root/name/"validation_report.json")
        if not check.get("passed") or check.get("errors"):raise ValueError("Preset not validated: "+name)
        if check.get("release_manifest_sha256")!=sha(root/name/"release_manifest.json"):
            raise ValueError("Preset validation is stale: "+name)
    release=read(root/"release_manifest.json")
    for name,expected in release["files_sha256"].items():
        if sha(root/name)!=expected:raise ValueError("Artifact changed after validation: "+name)
    archive=root/(root.name+".zip")
    names=sorted(set(release["files_sha256"])|{"release_manifest.json","validation_report.json", "document_holdout/validation_report.json", "rationale_core/validation_report.json"})
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zipout:
        for name in names:zipout.write(root/name,arcname=root.name+"/"+name)
    with zipfile.ZipFile(archive) as zipin:
        error=zipin.testzip()
        if error:raise ValueError("ZIP CRC failure: "+error)
    dump(root/"bundle_info.json",{"path":str(archive.resolve()),"bytes":archive.stat().st_size,"sha256":sha(archive),
                                   "files":len(names),"validation_report_sha256":sha(root/"validation_report.json")})
    print(json.dumps(read(root/"bundle_info.json"),ensure_ascii=False,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--dataset",type=Path,required=True)
    parser.add_argument("--workspace",type=Path,default=Path(__file__).resolve().parents[3])
    parser.add_argument("--stage",choices=["manifest","package"],required=True)
    args=parser.parse_args()
    if args.stage=="manifest":manifest(args.dataset,args.workspace)
    else:package(args.dataset)
