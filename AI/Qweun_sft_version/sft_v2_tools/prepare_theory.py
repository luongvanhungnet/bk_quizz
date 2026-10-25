"""Create reproducible source-grounded contrast quizzes from completed native text.

This deliberately makes a bounded concept-discrimination pilot, not synthetic
expert certification or unverified free-form teacher explanations.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import hashlib
import math
from pathlib import Path
import random
import re
import sqlite3
import sys
import unicodedata

from common import SEED, canonical, digest, encode, load, norm, read_rows, save, sha, write_rows
from quality import compact_score, hydrate
from concepts import canonical_concept

ROOT = Path(__file__).resolve().parents[1]
CPT = ROOT.parent/"data_preprocessing/training_releases/cpt_27courses_20261023"
WORK = ROOT/"datasets/theory_sft_v2_20261025"
OLD = ROOT/"datasets/sft_completed_native_20261025/payload"
N_TRAIN, N_VALIDATION, N_TEST, N_REPLAY = 270, 30, 100, 27
BAD = re.compile(r"giảng viên|sinh viên|hướng dẫn của gv|yêu cầu của gv|điện thoại|email|https?://|www\.|copyright|mục lục|tài liệu tham khảo|bài tập|câu hỏi|đáp án|hình ảnh|hình vẽ|đăng ký|đào tạo|liên hệ|học phí|điểm thi|slide|tham khảo|ví dụ|ví du|[\ue000-\uf8ff\ufffd]", re.I)
GENERIC = re.compile(r"^(?:chương|bài\s+\d|mục\s+\d|định nghĩa$|khái niệm$|các bước|kết quả$|lưu ý|nhận xét|chú ý|ghi chú|thực hành|lời khuyên|chi tiết|mục tiêu|nội dung|giả\s*thiết|giả sử|mô tả$|tên gọi|gồm$|bao gồm$|đừng|cần phải|yêu cầu$|với\b|nếu\b|vì\b|ta\b|chúng\b|nó\b|đây\b|đó\b|họ\b|nào$|nhận\s|chọn\s|thực hiện|sử dụng|một số|cách$|note\b|notes\b|thường\b|thông thường|cũng\b|ý tưởng|vấn đề|khi\b|sau\b|trước\b|then\b|each\b|this\b|the\b|đầu vào$|đầu ra$|để\b|hiểu\b|điều\s|lý do|hàm.*thực hiện|bên nhận|bên gửi|trên\b|dưới\b|iso\s|đoạn chương trình|nguyên tắc$)", re.I)
REL = re.compile(r"\s+(?:được định nghĩa là|được gọi là|là|is defined as|is an|is a)\s+|:\s+")
BULLET = re.compile(r"^\s*(?:[•▪❖◼❑▶➢✓–□●○❏]|l(?=\s+[A-ZÀ-Ỹ]))\s*")
DANGLING = set("là của các những một và hoặc bởi từ trong trên dưới về để với cho theo có tại sự được mà như thì vẫn cũng lại chỉ đang đã sẽ this that the a an of to and or as in on with".split())
VIET = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZđĐàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ')
TECH_PREDICATE = re.compile(r'\b(?:cung cấp|gồm|được|dùng|hệ thống|tập hợp|cấu trúc|thuật toán|hoạt động|ngôn ngữ|phương pháp|xử lý|thực hiện|bộ nhớ|chuyển|định nghĩa|lưu trữ|tạo|biểu diễn|xác định|liên kết|quá trình|loại|kỹ thuật|method|algorithm|system|data|function|process|structure|model|means|type|operations|comput|program|memory|collection|set of|used|allows|return)\b',re.I)
SYSTEM = """Bạn soạn đúng một câu hỏi trắc nghiệm mới từ các mục lý thuyết được cung cấp. Chỉ dùng căn cứ trong evidence. Giữ đủ dữ kiện để người học trả lời mà không xem ngữ cảnh. Dùng nguyên văn bốn option_terms làm phương án, mỗi nội dung dùng đúng một lần; không thêm phương án khác. Tuân thủ type và focus_concepts. SINGLE_CHOICE có một đáp án; MULTIPLE_SELECT có hai đáp án. Lời giải có principle (căn cứ phân biệt), application (áp dụng vào câu hỏi), và distractor_explanations giải thích từng lựa chọn sai, đánh số option từ0. Chỉ trỏ evidence_ids, không tự gõ sourceId hoặc quote. Chỉ trả JSON có type,prompt,options,principle,application,distractor_explanations,evidence_ids; options gồm text và correct boolean. Không markdown."""


def paragraphs(text):
    """Return exact source spans, joining wrapped lines only for fact parsing."""
    lines = text.splitlines(keepends=True); start = None; end = 0; buffer = []
    for line in lines:
        stripped = line.strip()
        plain = BULLET.sub("", stripped)
        new = bool(BULLET.match(line)) or bool(REL.search(plain))
        if stripped.isdecimal() or stripped.startswith(('©', 'Tham khảo tài liệu')):
            if buffer: yield start, end, text[start:end]
            start = None; buffer = []; end += len(line); continue
        if not stripped or new and buffer:
            if buffer: yield start, end, text[start:end]
            start = None; buffer = []
        if stripped:
            if start is None: start = end
            buffer.append(line)
        end += len(line)
    if buffer: yield start, end, text[start:end]


def extract_facts(records):
    facts = []; rejected = Counter(); seen = set()
    curation = load(Path(__file__).with_name('curation_exclusions.json'))
    blocked = {(x['record_id'],x['quote_sha256']):x['reason'] for x in curation['exclusions']}
    blocked_meaning={(norm(x['concept']),norm(x['definition'])) for x in curation['exclusions']}
    for row in records:
        if row.get("vlm") is not False or row["record"].get("kind") != "text":
            rejected["not_completed_native_text"] += 1; continue
        text = row["text"]
        if text.strip() != row["record"].get("native_text", "").strip():
            rejected["native_bytes_edited_or_redacted"] += 1; continue
        if row["acceptance"] not in {"review_approve", "owner_default_pass"} or row["record"].get("split") != "train":
            raise ValueError("Only authorized completed CPT regions may be reused")
        for begin, end, quote in paragraphs(text):
            cleaned = " ".join(BULLET.sub("", line).strip() for line in quote.splitlines()).strip()
            cleaned = re.sub(r"\s+", " ", cleaned)
            if not 65 <= len(cleaned) <= 650 or BAD.search(cleaned): continue
            # Ignore two-column fragments and mathematical/font corruption.
            if any(re.search(r"\S {5,}\S", line.strip()) for line in quote.splitlines()): continue
            if any(x in cleaned for x in ("ð", "þ", "", "", "[EMAIL]", "…")): continue
            if any(c.isalpha() and c not in VIET for c in unicodedata.normalize('NFC',cleaned)): continue
            if any(c in cleaned for c in ('®','™','§','‡','†','˜','¶','£','ß','©')): continue
            match = REL.search(cleaned)
            if not match: continue
            subject = cleaned[:match.start()].strip(" •▪❖◼❑▶➢-0123456789.)\t")
            predicate = cleaned[match.end():].strip()
            if not 3 <= len(subject) <= 60 or not 6 <= len(predicate.split()) <= 70: continue
            if len(subject.split())>7 or not subject[0].isupper() and subject not in {'bool','char','int','float','double','k-means'}: continue
            if not subject[0].isalpha() or not TECH_PREDICATE.search(predicate):continue
            if GENERIC.search(subject) or any(c in subject for c in "=<>?{};") or subject.count("(") != subject.count(")"): continue
            if '?' in predicate or re.search(r"\s\d+[.)]\s", cleaned): continue
            if any(w in norm(subject).split() for w in ("có", "được", "nên", "cần", "sẽ", "phải")): continue
            if predicate.rstrip('.;,?!').split()[-1].casefold() in DANGLING or predicate.endswith((',', ':', '–', '-')): continue
            if any(word in norm(subject).split() for word in ("và", "hoặc", "thì")): continue
            if sum(c.isalpha() for c in cleaned)/len(cleaned) < .6: continue
            subject = canonical_concept(subject)
            if subject is None: continue
            quote_hash=hashlib.sha256(quote.encode()).hexdigest()
            if (row['id'],quote_hash) in blocked:
                rejected['editorial_'+blocked[row['id'],quote_hash]]+=1;continue
            if (norm(subject),norm(predicate.rstrip('.;'))) in blocked_meaning:
                rejected['editorial_repeated_rejected_definition']+=1;continue
            predicate=re.sub(r'^là\s+','',predicate,flags=re.I)
            if norm(predicate).startswith(norm(subject)+' là '):predicate=predicate[len(subject):].strip()[3:]
            key = norm(subject)+"|"+norm(predicate)
            if key in seen: continue
            seen.add(key)
            fact = {"concept": subject, "definition": predicate.rstrip(".;"), "quote": quote,
                    "record_id": row["id"], "document_id": row["document_id"], "course": row["course"],
                    "page": row["page"], "page_block": (row["page"]-1)//16,
                    "source_sha256": row["source_sha256"], "source_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "source_span": [begin, end], "source_quote_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                    "extraction": "completed_native_text_verbatim_span", "source_acceptance": row["acceptance"],
                    "source_human_reviewed": row["human_verified"], "cpt_seen": True}
            fact["quality_rank"] = (3 if match.group().strip() != ':' else 0)+(2 if predicate.endswith('.') else 0)+min(3, len(predicate.split())//8)
            fact["id"] = "fact_"+digest(fact)[:24]; facts.append(fact)
    return facts, dict(rejected)


def split_sources(facts):
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x: parent[x] = find(parent[x])
        return parent[x]
    def union(x, y):
        x, y = find(x), find(y)
        if x != y: parent[max(x, y)] = min(x, y)
    concepts = {}; exact = {}
    for f in facts:
        block = f["document_id"]+":b"+str(f["page_block"]); f["block_id"] = block; find(block)
        for mapping, key in ((concepts, norm(f["concept"])), (exact, norm(f["quote"]))):
            if key in mapping: union(block, mapping[key])
            else: mapping[key] = block
    # Four entire documents held out; all blocks tied by duplicated concepts follow them.
    course_counts = Counter(f["course"] for f in facts)
    eligible = [c for c, n in course_counts.items() if n >= 20]
    held_courses = sorted(eligible, key=lambda c: digest({"doc_holdout": c, "seed": SEED}))[:2]
    held_groups = {find(f["block_id"]) for f in facts if f["course"] in held_courses}
    for f in facts:
        group = find(f["block_id"])
        value = int(digest({"source_group": group, "seed": SEED})[:8], 16)%100
        split = "test" if group in held_groups else "train" if value < 65 else "validation" if value < 92 else "test"
        f.update(split=split, split_group=group, test_scope="unseen_sft_document" if f["course"] in held_courses else "heldout_sft_page_block")
    return {"heldout_courses": held_courses, "policy": "whole16page_blocks_union_exact_concepts_and_exact_text_plus2_document_holdouts",
            "independent_from_v2_sft": True, "unseen_by_legacy_cpt": False,
            "fact_counts": dict(Counter(f["split"] for f in facts)), "source_courses": dict(course_counts)}


def terms(text): return set(re.findall(r"[^\W\d_]{3,}", norm(text))) - {"các", "một", "trong", "được", "không", "với", "cho", "the", "and", "that"}


def choose_related(fact, pool):
    target_terms = terms(fact["definition"]+" "+fact["concept"])
    choices = []
    for other in pool:
        if other["id"] == fact["id"] or norm(other["concept"]) == norm(fact["concept"]): continue
        if norm(other["concept"]) in norm(fact["concept"]) or norm(fact["concept"]) in norm(other["concept"]): continue
        if SequenceMatcher(None, norm(other["definition"]), norm(fact["definition"])).ratio() > .72: continue
        other_terms = terms(other["definition"]+" "+other["concept"])
        score = len(target_terms & other_terms)/max(1, len(target_terms | other_terms))
        proximity = abs(other["page"]-fact["page"])
        choices.append((score, -proximity, digest(other["id"]), other))
    result = [fact]
    for _, _, _, other in sorted(choices, key=lambda x: x[:3], reverse=True):
        if all(SequenceMatcher(None, norm(other["concept"]), norm(x["concept"])).ratio() < .8
               and SequenceMatcher(None,norm(other['definition']),norm(x['definition'])).ratio()<.8 for x in result):
            result.append(other)
        if len(result) == 4: return result
    return []


def make_sample(fact, related, variant):
    rng = random.Random(int(digest(fact["id"]+str(variant))[:12], 16))
    multi = variant % 3 == 2
    reverse = variant % 3 == 1
    targets = related[:2] if multi else [fact]
    options_order = list(related); rng.shuffle(options_order)
    evidence = [{"id": "E"+str(i+1), "text": f["quote"], "source_id": f["record_id"],
                 "source_sha256": f["source_sha256"], "page": f["page"], "fact_id": f["id"]} for i, f in enumerate(related)]
    ev_ids = {f["id"]: e["id"] for f, e in zip(related, evidence)}
    options = [{"text": f["definition"] if reverse else f["concept"], "correct": f in targets} for f in options_order]
    if multi:
        prompt = "Chọn hai khái niệm tương ứng với hai mô tả theo tài liệu: (1) "+targets[0]["definition"]+"; (2) "+targets[1]["definition"]+"."
    elif reverse:
        prompt = "Theo tài liệu, mô tả nào phù hợp với khái niệm “"+fact["concept"]+"”?"
    else:
        intro = ("Khái niệm nào được tài liệu mô tả như sau: ", "Trong các thuật ngữ sau, thuật ngữ nào khớp với mô tả: ",
                 "Đối chiếu các khái niệm trong tài liệu, mô tả sau thuộc khái niệm nào: ", "Một mục lý thuyết có đặc trưng sau. Hãy chọn đúng tên khái niệm: ")[variant % 4]
        prompt = intro+fact["definition"]+"?"
    principle = "Phân biệt các thuật ngữ bằng nội dung định nghĩa, thay vì chỉ dựa vào từ xuất hiện giống nhau. " + " ".join(
        f["concept"]+": "+f["definition"]+"." for f in targets)
    application = "Mô tả trong câu hỏi khớp "+" và ".join(f["concept"] for f in targets)+" theo "+", ".join(ev_ids[f["id"]] for f in targets)+". Vì vậy chọn "+", ".join(chr(65+i) for i, o in enumerate(options) if o["correct"])+"."
    reasons = [{"option": i, "reason": f["concept"]+" được mô tả là “"+f["definition"]+"”; đây là cặp khái niệm–mô tả khác với mục đang hỏi.",
                "evidence_ids": [ev_ids[f["id"]]]} for i, f in enumerate(options_order) if f not in targets]
    reference = {"type": "MULTIPLE_SELECT" if multi else "SINGLE_CHOICE", "prompt": prompt, "options": options,
                 "principle": principle, "application": application, "distractor_explanations": reasons,
                 "evidence_ids": [ev_ids[f["id"]] for f in targets]}
    user = {"task": "theory_to_concept_contrast_quiz", "course": fact["course"], "type": reference["type"],
            "focus_concepts": [f["concept"] for f in targets], "option_terms": [o["text"] for o in options],
            "evidence": [{"id": e["id"], "text": e["text"]} for e in evidence]}
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": canonical(user).decode()},
                {"role": "assistant", "content": canonical(reference).decode()}]
    sample = {"id": "v2_"+digest({"target": fact["id"], "mode": variant%3, "version": 2})[:24], "course": fact["course"],
              "split": fact["split"], "split_group": fact["split_group"], "context_groups": sorted({f["split_group"] for f in related}),
              "test_scope": fact["test_scope"], "evidence": evidence, "reference": reference, "messages": messages,
              "gold_texts": [o["text"] for o in options if o["correct"]],
              "required_prompt_fragments": [fact["concept"]] if reverse else sorted({n for f in targets for n in re.findall(r"\b\d+(?:[.,]\d+)?\b", f["definition"])}),
              "prompt_content_tokens": [] if reverse else sorted({w for f in targets for w in terms(f["definition"]) if len(w) > 3}, key=lambda w: (-len(w), w))[:12],
              "question_mode": "term_to_definition" if reverse else "two_definition_match" if multi else "definition_to_term",
              "target_fact_id": fact["id"], "context_fact_ids": [f["id"] for f in related],
              "authoring": "deterministic_source_fact_contrast", "quality_checked": "exact_source_spans_mapping_schema_split_and_token_masks",
              "training_task": "theory_to_quiz",
              "human_verified": False, "expert_semantically_verified": False,
              "coverage": "concept_discrimination_with_three_part_evidence_grounded_explanation; not unrestricted_scenario_generation"}
    if not compact_score(messages[-1]["content"], sample)["usable_proxy"]: raise ValueError("Invalid reference")
    return sample


def prepare(work=WORK):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    manifest = load(CPT/"colab/data/manifest.json")
    for name, wanted in manifest["files_sha256"].items():
        if sha(CPT/"colab"/name) != wanted: raise ValueError("Frozen CPT export changed")
    records = read_rows(CPT/"final_selection.jsonl")
    exported = read_rows(CPT/"colab/data/train.jsonl")
    sources = read_rows(CPT/"colab/data/sources.jsonl")
    if len(records) != len(exported) or any(r["text"] != t["text"] or r["id"] != s["id"] for r, t, s in zip(records, exported, sources)):
        raise ValueError("Native source selection is not the actual completed CPT corpus")
    facts, excluded = extract_facts(records)
    split_report = split_sources(facts)
    save(work/"split_lock.json", {"assignments": {f["id"]: {"split": f["split"], "group": f["split_group"]} for f in facts},
         "assigned_before_question_generation": True, "scope": split_report})
    groups = defaultdict(list)
    for f in facts: groups[f["course"], f["split"]].append(f)
    candidates = []; extra_candidates = []; rejected = Counter(); token_lengths = []
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(OLD/"tokenizer"), local_files_only=True, trust_remote_code=False)
    old_questions = [norm(q["prompt"]) for q in read_rows(OLD/"source_questions.jsonl")]
    old_words = [terms(stem) for stem in old_questions]
    for fact in sorted(facts, key=lambda f: (-f["quality_rank"], digest(f["id"]))):
        related = choose_related(fact, groups[fact["course"], fact["split"]])
        if not related: rejected["insufficient_distinct_related_concepts"] += 1; continue
        mode = int(digest(fact['id'])[:6],16)%3
        sample = make_sample(fact, related, mode)
        # This release does not reuse an existing exam stem or source answer.
        prompt_words = terms(sample["reference"]["prompt"])
        if any(len(prompt_words & words)/max(1, len(prompt_words | words)) > .65 and SequenceMatcher(None, norm(sample["reference"]["prompt"]), stem).ratio() > .82 for stem, words in zip(old_questions, old_words)):
            rejected["near_existing_exam_prompt"] += 1; continue
        try: tokens = encode(tok, sample["messages"], sample["id"])
        except ValueError: rejected["overlength_or_reserved_chat_token"] += 1; continue
        sample["token_count"] = len(tokens["input_ids"]); candidates.append(sample)
        if fact['split'] in {'train','validation','test'}:
            for second_mode in ((mode+1)%3,(mode+2)%3):
                extra=make_sample(fact,related,second_mode)
                try:extra_tokens=encode(tok,extra['messages'],extra['id'])
                except ValueError:continue
                extra['token_count']=len(extra_tokens['input_ids']);extra_candidates.append(extra)
    candidates.extend(extra_candidates)
    # Balanced round robin over all eligible courses, no repeated targets or padding to count.
    def balanced(split, count):
        queues = defaultdict(list); additional = defaultdict(list); targets=set()
        for s in candidates:
            if s["split"] != split:continue
            if s['target_fact_id'] not in targets:
                queues[s['course']].append(s);targets.add(s['target_fact_id'])
            else:additional[s['course']].append(s)
        chosen = []
        for phase in (queues,additional):
            while phase and len(chosen) < count:
                for course in sorted(list(phase)):
                    if not phase[course]:del phase[course];continue
                    chosen.append(phase[course].pop(0))
                    if len(chosen)==count:break
        if len(chosen) < count: raise ValueError(f"Only {len(chosen)} eligible {split} samples; refuse fabricating/padding {count}")
        return chosen
    selected = balanced("train", N_TRAIN)+balanced("validation", N_VALIDATION)+balanced("test", N_TEST)
    by_id = {f["id"]: f for f in facts}
    # A bounded10% rehearsal mix, drawn only from the already locked training sources.
    train_rows = [s for s in selected if s["split"] == "train"]
    for i, sample in enumerate(train_rows[-N_REPLAY:]):
        if i % 2 == 0:
            sample["training_task"] = "source_grounded_qa"
            user = {"task": "source_grounded_qa", "question": "Theo nguồn, “"+by_id[sample["target_fact_id"]]["concept"]+"” được mô tả như thế nào?",
                    "evidence": [{"id": e["id"], "text": e["text"]} for e in sample["evidence"]]}
            answer = {"answer": by_id[sample["target_fact_id"]]["definition"], "evidence_ids": ["E1"]}
            system = 'Chỉ dùng evidence được cung cấp. Trả duy nhất JSON có answer (chuỗi) và evidence_ids (mảng ID). Không markdown hoặc nội dung thêm.'
        else:
            sample["training_task"] = "closed_book_mcq_format"
            user = {"task": "closed_book_mcq_format", "prompt": sample["reference"]["prompt"],
                    "options": [{"label": chr(65+j), "text": o["text"]} for j, o in enumerate(sample["reference"]["options"])]}
            answer = {"correct_labels": [chr(65+j) for j, o in enumerate(sample["reference"]["options"]) if o["correct"]]}
            system = 'Chọn các phương án đúng. Chỉ trả duy nhất JSON có correct_labels là mảng nhãn phương án. Không giải thích hoặc nhắc lại chỉ dẫn.'
        sample["replay_reference"] = answer
        sample["messages"] = [{"role": "system", "content": system}, {"role": "user", "content": canonical(user).decode()},
                              {"role": "assistant", "content": canonical(answer).decode()}]
        sample["token_count"] = len(encode(tok, sample["messages"], sample["id"])["input_ids"])
    for s in selected:
        if any(by_id[i]["split"] != s["split"] for i in s["context_fact_ids"]): raise ValueError("Retrieval crosses split")
    concepts_by_split = defaultdict(set); groups_by_split = defaultdict(set)
    for s in selected:
        for fid in s["context_fact_ids"]:
            f = by_id[fid]; concepts_by_split[s["split"]].add(norm(f["concept"])); groups_by_split[s["split"]].add(f["split_group"])
    for a, b in (("train", "validation"), ("train", "test"), ("validation", "test")):
        if concepts_by_split[a] & concepts_by_split[b] or groups_by_split[a] & groups_by_split[b]: raise ValueError("Concept or page-group leakage")
    write_rows(work/"facts.jsonl", facts)
    for split in ("train", "validation", "test"):
        rows = [s for s in selected if s["split"] == split]
        write_rows(work/(split+".samples.jsonl"), rows)
        write_rows(work/(split+".messages.jsonl"), [{"id": s["id"], "messages": s["messages"]} for s in rows])
        write_rows(work/(split+".tokenized.jsonl"), [encode(tok, s["messages"], s["id"]) for s in rows])
        write_rows(work/(split+".quiz_preview.jsonl"), [{"id": s["id"], "quiz": hydrate(s["reference"], s["evidence"]),
                                                       "human_verified": False} for s in rows])
    # Retrieval index is reproducible and train-only by default. Test never enters training retrieval.
    from retrieval import rebuild
    rebuild(work/"retrieval.sqlite3", facts)
    report = {"counts": dict(Counter(s["split"] for s in selected)), "source_fact_count": len(facts),
        "eligible_candidates": len(candidates), "selected_courses": dict(Counter(s["course"] for s in selected)),
        "split_courses": {sp: dict(Counter(s["course"] for s in selected if s["split"] == sp)) for sp in ("train", "validation", "test")},
        "question_types": dict(Counter(s["reference"]["type"] for s in selected)), "split_report": split_report,
        "training_task_mix": dict(Counter(s["training_task"] for s in selected if s["split"] == "train")),
        "selected_unique_target_facts": {sp:len({s['target_fact_id'] for s in selected if s['split']==sp}) for sp in ('train','validation','test')},
        "concept_whitelist_sha256":sha(Path(__file__).with_name('concepts.py')),
        "editorial_exclusions_sha256":sha(Path(__file__).with_name('curation_exclusions.json')),
        "source_exclusions": excluded, "candidate_exclusions": dict(rejected),
        "token_length_max": max(s["token_count"] for s in selected), "old_exam_stems_reused": 0,
        "new_ocr_or_vlm_calls": 0, "human_approvals_created": 0, "expert_accuracy_certified": False,
        "source_selection_sha256": sha(CPT/"final_selection.jsonl"), "source_manifest_sha256": sha(CPT/"colab/data/manifest.json"),
        "quality_scope": "deterministic source-aligned concept contrast pilot; not expert-certified deep scenario reasoning"}
    save(work/"PREPARATION_REPORT.json", report)
    save(work/"manifest.json", {"schema": "bkquiz-theory-sft-v2", "counts": report["counts"], "model": "Qwen/Qwen3-1.7B",
        "base_revision": "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e", "source_policy": "completed_native_text_only",
        "test_used_for_selection": False, "human_verified": False, "expert_semantically_verified": False,
        "files_sha256": {p.name: sha(p) for p in work.iterdir() if p.is_file() and p.name not in {"manifest.json"} and p.suffix in {".json", ".jsonl", ".sqlite3"}}})
    print(canonical(report).decode(), flush=True)
    return report


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    prepare(Path(sys.argv[1]) if len(sys.argv) > 1 else WORK)
