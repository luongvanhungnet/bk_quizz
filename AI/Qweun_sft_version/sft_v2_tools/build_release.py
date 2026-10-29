"""Package three separate Colab tasks and keep the final test out of training."""
from __future__ import annotations
import ast
from collections import Counter
from pathlib import Path
import shutil
import sys

from common import canonical, digest, load, make_zip, read_rows, save, sha, verify_files, write_rows
from prepare_theory import ROOT, WORK, OLD, SYSTEM, N_TRAIN, N_VALIDATION, N_TEST, N_REPLAY
from retrieval import rebuild

HERE = Path(__file__).resolve().parent
RELEASE = ROOT/'sft_v2_releases/theory_v2_curated_20261025'
FOUR = ROOT/'model_comparisons/four_way_20261025'
DRIVE_FOLDER = 'BKQuiz_CPT/SFT_V2_THEORY_20261025'
RUNTIME_FILES = ('common.py', 'quality.py', 'constrained.py', 'engine.py', 'preflight.py', 'retrieval.py', 'rag_quiz.py', 'train_v2.py', 'evaluate_v2.py', 'diagnose.py')


def runtime(root):
    rt = root/'runtime'; rt.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_FILES: shutil.copyfile(HERE/name, rt/name)
    for name, src in (('legacy_scoring.py', FOUR/'input/runtime/scoring.py'), ('quiz_schema.py', FOUR/'input/runtime/quiz_schema.py')):
        shutil.copyfile(src, rt/name)
    tree = ast.parse((HERE/'prepare_theory.py').read_text(encoding='utf-8'))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'terms', 'choose_related', 'make_sample'}]
    (rt/'planning.py').write_text('import random,re\nfrom difflib import SequenceMatcher\nfrom common import canonical,digest,norm\nfrom quality import compact_score\nSYSTEM='+repr(SYSTEM)+'\n\n'+'\n\n'.join(ast.unparse(n) for n in functions), encoding='utf-8')
    req = (OLD/'runtime/requirements.txt').read_text(encoding='utf-8')
    (rt/'requirements.txt').write_text(req+'\nlm-format-enforcer==0.11.3\ninteregular==0.3.3\npydantic==2.14.1\n', encoding='utf-8')
    save(rt/'train_config.json', {'epochs': 1, 'learning_rate': 2e-5, 'gradient_accumulation_steps': 8,
        'quality_max_new_tokens': 1536, 'selection': 'fixed4validation_generation_proxy_then_NLL_tiebreak'})
    shutil.copytree(OLD/'tokenizer', root/'tokenizer', dirs_exist_ok=True)


def dataset(root, splits):
    target = root/'data'; target.mkdir(parents=True, exist_ok=True)
    source_manifest = verify_files(WORK)
    for split in splits:
        for suffix in ('samples.jsonl', 'messages.jsonl', 'tokenized.jsonl', 'quiz_preview.jsonl'):
            shutil.copyfile(WORK/(split+'.'+suffix), target/(split+'.'+suffix))
    facts = [f for f in read_rows(WORK/'facts.jsonl') if f['split'] in splits]
    write_rows(target/'facts.jsonl', facts)
    shutil.copyfile(WORK/'split_lock.json', target/'split_lock.json')
    if 'train' in splits: rebuild(target/'retrieval.sqlite3', facts)
    save(target/'manifest.json', {'schema': 'bkquiz-theory-sft-v2', 'source_policy': 'completed_native_text_only',
        'counts': {s: source_manifest['counts'][s] for s in splits}, 'source_full_manifest_sha256': sha(WORK/'manifest.json'),
        'expert_semantically_verified': False, 'human_verified': False,
        'files_sha256': {p.name: sha(p) for p in target.iterdir() if p.is_file() and p.name != 'manifest.json'}})


def seal(root, extra):
    registry = {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*')) if p.is_file() and p != root/'manifest.json' and '__pycache__' not in p.parts}
    save(root/'manifest.json', {'schema': 'bkquiz-sft-v2-input-v1', 'files_sha256': registry, **extra})
    return sha(root/'manifest.json')


def notebook(kind, archive, expected):
    names = {'diagnostics': '01_Diagnose_Schema_4Models.ipynb', 'train': '02_Train_Base_SFTv2_RAG.ipynb', 'test': '03_Independent_Test_100.ipynb'}
    titles = {'diagnostics': 'Đối chứng structured decoding trên4bản hiện có', 'train': 'Base → SFT-v2 từ lý thuyết native, kèm RAG', 'test': '100câu test từ nhóm nguồn giữ riêng: Base và SFT-v2'}
    cells = []
    def add(kind_, text):
        if kind_ == 'code': ast.parse(text)
        c = {'cell_type': kind_, 'id': 'v2-'+str(len(cells)), 'metadata': {}, 'source': text.strip().splitlines(keepends=True)}
        if kind_ == 'code': c.update(execution_count=None, outputs=[])
        cells.append(c)
    md = lambda text: add('markdown', text)
    code = lambda text: add('code', text)
    md('# BKQuiz · '+titles[kind]+'''\nChọn **Runtime → Change runtime type → T4 GPU**, rồi **Run all**.
Không chạy OCR/VLM hoặc teacher7B. Giữ CUDA torch của Colab; cài đặt hiện đầy đủ log.
Người dùng tự chạy GPU. Notebook mới không thay notebook/model đang phục vụ.
''')
    if kind == 'diagnostics': md('''Dùng đúng3adapter đã có và base pinned, không train lại.
40MCQ/12quiz cũ trở thành regression/dev. So sánh output raw đã trả về với structured decoding;
không sửa JSON cũ rồi thay điểm. Runtime cần T4/FP16 và phiên bản giống lần trước.
Schema chặn lỗi cú pháp; không chứng minh đáp án/lời giải đúng. Bước này có thể mất gần hoặc hơn1h.
''')
    elif kind == 'train': md('''**270train =243quiz lý thuyết +14QA từ nguồn +13MCQ giữ định dạng;30validation.**
Đây là pilot đối chiếu khái niệm dùng4thuật ngữ kiểm soát, với ba phần giải thích từ nguồn;
không phải bộ tình huống chuyên sâu được chuyên gia chứng nhận. Source text native đã hoàn tất.
Không có text/đáp án test trong ZIP train. Fresh LoRA trên base Qwen3-1.7B; không nạp CPT.
1epoch mặc định; chọn checkpoint qua4mẫu validation generation cố định, source-answer và cấu trúc;
NLL chỉ phá hòa. Các chỉ số này là proxy, chưa phải expert approval. Test chạy riêng ở notebook03.
''')
    else: md('''100câu tham chiếu máy được giữ riêng từ trước train; gồm nhóm trang giữ lại và2tài liệu
không có trong train SFT-v2. CPT cũ đã học27PDF, vì vậy không gọi đây là unseen-CPT.
Không dùng test để chọn checkpoint. Đầu vào generation có source cards chuẩn (oracle context),
không đo retrieval recall. Mặc định chạy **đủ100MCQ và100quiz cho từng bản**; cache theo từng batch.
Đây là bước dài nhất, có thể mất vài giờ trên T4. Batch2mặc định; dùng4nếu GPU đủ RAM.
Muốn chạy nhanh20/50quiz thì đổi GENERATION_LIMIT trước lần đầu và đổi RUN_NAME;
báo cáo luôn giữ đúng mẫu số, không gọi mẫu nhỏ là100quiz đã đánh giá.
''')
    code("from google.colab import drive\ndrive.mount('/content/drive')\nfrom pathlib import Path\nimport os,sys,hashlib,zipfile,shutil,stat,json\nfrom pathlib import PurePosixPath\n")
    code(f"DRIVE_ROOT=Path('/content/drive/MyDrive/{DRIVE_FOLDER}')\nZIP_PATH=DRIVE_ROOT/{archive!r}\nEXPECTED_SHA256={expected!r}\nRUN_NAME={('schema_diag_001' if kind == 'diagnostics' else 'sft_v2_001' if kind == 'train' else 'final_test_001')!r}\n"
         +("TRAIN_RUN_NAME='sft_v2_001'\nBATCH_SIZE=2\nGENERATION_LIMIT=100\n" if kind == 'test' else 'EPOCHS=1  # thử2với RUN_NAME mới; chọn bằng validation trước test\n' if kind=='train' else ''))
    code('''def file_sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
assert ZIP_PATH.is_file(), str(ZIP_PATH)
LOCAL_ZIP=Path('/content')/ZIP_PATH.name
shutil.copyfile(ZIP_PATH,LOCAL_ZIP)
assert file_sha(LOCAL_ZIP)==EXPECTED_SHA256, 'Notebook vàZIP không cùng bản'
WORK=Path('/content/bkquiz_v2_'+EXPECTED_SHA256[:12]);WORK.mkdir(exist_ok=True)
with zipfile.ZipFile(LOCAL_ZIP) as z:
    infos=z.infolist(); names=[i.filename for i in infos]
    assert len(names)==len(set(names)) and len(names)<1000 and sum(i.file_size for i in infos)<512*1024*1024
    for i in infos:
        r=PurePosixPath(i.filename)
        assert not r.is_absolute() and '..' not in r.parts and ':' not in i.filename and chr(92) not in i.filename
        assert stat.S_IFMT(i.external_attr>>16)!=stat.S_IFLNK and i.file_size<128*1024*1024
        assert (WORK/i.filename).resolve().is_relative_to(WORK.resolve())
    m=json.loads(z.read('manifest.json'));assert set(names)=={'manifest.json',*m['files_sha256']}
    z.extractall(WORK)
for name,wanted in m['files_sha256'].items(): assert file_sha(WORK/name)==wanted,name
RUNTIME=WORK/'runtime'
RUN=DRIVE_ROOT/'runs'/RUN_NAME;RUN.mkdir(parents=True,exist_ok=True)
''')
    helper = (HERE/'completed_native/colab_bootstrap.py').read_text(encoding='utf-8')
    code(helper+'\n'+'''VENV=Path('/content/bkquiz_sft_v2_venv')
PYTHON=ensure_colab_venv(VENV)
(RUNTIME/'sitecustomize.py').write_text("import importlib.util\\n_original=importlib.util.find_spec\\ndef _find(name,*args,**kwargs):\\n    if name.split('.')[0] in {'torchvision','torchaudio','librosa'}:return None\\n    return _original(name,*args,**kwargs)\\nimportlib.util.find_spec=_find\\n",encoding='utf-8')
ENV=dict(os.environ,PYTHONPATH=str(RUNTIME),TOKENIZERS_PARALLELISM='false')
run_logged([PYTHON,'-m','pip','install','-r',RUNTIME/'requirements.txt'],env=ENV,log_path=RUN/'setup.log')
run_logged([PYTHON,'-c','import torch; assert torch.cuda.is_available(), "Select GPU runtime"; print(torch.__version__,torch.cuda.get_device_properties(0))'],env=ENV,log_path=RUN/'setup.log')
def launch(script,*args):
    run_logged([PYTHON,'-u',RUNTIME/script,*map(str,args)],env=ENV,cwd=RUNTIME,log_path=RUN/'execution.log')
''')
    if kind == 'diagnostics':
        code('''launch('diagnose.py','--root',WORK,'--mode','preflight')
for variant in ('base','cpt','sft','cpt_sft'):
    launch('diagnose.py','--root',WORK,'--output',RUN/'evaluation','--variant',variant)
launch('diagnose.py','--root',WORK,'--output',RUN/'evaluation','--mode','report')
OUTPUT=RUN/'schema_diagnostics_results.zip'
with zipfile.ZipFile(OUTPUT,'w',zipfile.ZIP_DEFLATED) as z:
    for p in (RUN/'evaluation').rglob('*'):
        if p.is_file(): z.write(p,p.relative_to(RUN/'evaluation').as_posix())
''')
    elif kind == 'train':
        code('''launch('train_v2.py','--root',WORK,'--mode','preflight')
TRAIN=RUN/'train'
args=['--root',WORK,'--output',TRAIN,'--epochs',EPOCHS]
if (TRAIN/'identity.json').is_file(): args+=['--resume']
launch('train_v2.py',*args)
OUTPUT=TRAIN/'sft_v2_adapter.zip'
print('Selected adapter:',TRAIN/'adapter')
print('Final test chỉ chạy từ notebook03; không có dữ liệu test trong input này.')
''')
        md('''## Thử RAG trên nguồn train
Chỉ truy xuất source cards thuộc train, dùng model chọn evidence ID rồi code gắn quote nguyên văn.
Đây là bản mẫu CLI, chưa thay backend/model đang phục vụ. Output không qua proxy sẽ được giữ để xem lỗi.
''')
        code('''DO_RAG_DEMO=True
if DO_RAG_DEMO:
    facts=[json.loads(line) for line in (WORK/'data/facts.jsonl').read_text(encoding='utf-8').splitlines()]
    example=next(f for f in facts if f['split']=='train' and f['course']=='IT3070')
    launch('rag_quiz.py','--root',WORK,'--query',example['concept'],'--course',example['course'],
           '--sft-run',TRAIN,'--output',RUN/'rag_demo.json')
''')
    else:
        code('''SFT_RUN=DRIVE_ROOT/'runs'/TRAIN_RUN_NAME/'train'
assert (SFT_RUN/'completed.json').is_file(), 'Chạy notebook02 trước hoặc sửa TRAIN_RUN_NAME cho đúng'
launch('evaluate_v2.py','--root',WORK,'--mode','preflight')
for variant in ('base','sft_v2'):
    launch('evaluate_v2.py','--root',WORK,'--output',RUN/'evaluation','--sft-run',SFT_RUN,
           '--variant',variant,'--batch-size',BATCH_SIZE,'--generation-limit',GENERATION_LIMIT)
launch('evaluate_v2.py','--root',WORK,'--output',RUN/'evaluation','--mode','report')
OUTPUT=RUN/'evaluation/sft_v2_final_test_results.zip'
from IPython.display import Markdown,display
display(Markdown((RUN/'evaluation/FINAL_TEST.md').read_text(encoding='utf-8')))
''')
    code("from google.colab import files\nassert OUTPUT.is_file(), 'Chưa có kết quả hoàn chỉnh'\nprint('Lưu trên Drive:',OUTPUT)\nfiles.download(str(OUTPUT))\n")
    md('''Giữ RUN_NAME để tiếp tục cache/checkpoint cùng cấu hình. Khi đổi code, dataset, thư viện,
batch hoặc số mẫu, dùng RUN_NAME mới. Nếu chưa có checkpoint đầu tiên, cần run mới để train lại từ đầu.
Các cờ human_verified/expert_semantically_verified vẫn false nếu chưa có lượt duyệt thật.
''')
    nb = {'nbformat': 4, 'nbformat_minor': 5, 'metadata': {'colab': {'name': names[kind], 'gpuType': 'T4'},
          'kernelspec': {'display_name': 'Python3', 'language': 'python', 'name': 'python3'}, 'accelerator': 'GPU'}, 'cells': cells}
    return names[kind], nb


def build():
    RELEASE.mkdir(parents=True, exist_ok=True)
    if (RELEASE/'PUBLISHED.json').exists(): raise ValueError('Published release is frozen; choose a new version')
    verify_files(FOUR/'input','comparison_manifest.json')
    # Diagnostic input contains only already trained adapter weights and old dev cases.
    diag = RELEASE/'diagnostics_input'; runtime(diag)
    for variant, src in (('cpt', FOUR/'input/data/assets/cpt_adapter'), ('cpt_sft', FOUR/'input/models/cpt_sft'),
                         ('sft', FOUR/'returned_analysis/extracted/sft_only_training/adapter')):
        target = diag/'models'/variant; target.mkdir(parents=True, exist_ok=True)
        expected=load(FOUR/'returned_analysis/extracted'/variant/'identity.json')['adapter_sha256']
        for n in ('adapter_config.json', 'adapter_model.safetensors'):
            if sha(src/n)!=expected[n]:raise ValueError('Wrong existing '+variant+' adapter')
            shutil.copyfile(src/n, target/n)
    for src, dst in ((FOUR/'input/tasks.json', 'legacy_tasks.json'), (FOUR/'returned_analysis/extracted/comparison.json', 'baseline_comparison.json'),
                     (FOUR/'returned_analysis/extracted/base/identity.json', 'baseline_identity.json')):
        shutil.copyfile(src, diag/dst)
    save(diag/'baseline_records.json',{v:{p.stem:load(p)['record'] for p in (FOUR/'returned_analysis/extracted'/v/'samples').glob('*.json')} for v in ('base','cpt','sft','cpt_sft')})
    old = load(FOUR/'input/comparison_manifest.json')
    seal(diag, {'scope': 'old_test_is_now_regression_dev', 'legacy_generation_ids': old['generation_order'][:12]})
    train = RELEASE/'training_input'; runtime(train); dataset(train, ('train', 'validation'))
    validation = read_rows(train/'data/validation.samples.jsonl'); chosen = []; courses = set()
    for kind in ('MULTIPLE_SELECT', 'SINGLE_CHOICE', 'MULTIPLE_SELECT', 'SINGLE_CHOICE'):
        row = next((s for s in validation if s['reference']['type'] == kind and s['course'] not in courses), None)
        if row is None: row = next(s for s in validation if s['id'] not in chosen)
        chosen.append(row['id']); courses.add(row['course'])
    save(train/'validation_generation_ids.json', chosen)
    train_sha = seal(train, {'purpose': 'fresh_base_sft_training_no_test_content', 'contains_test_text_or_answers': False,
                            'test_source_lock_sha256': sha(WORK/'split_lock.json')})
    test = RELEASE/'test_input'; runtime(test); dataset(test, ('test',))
    seal(test, {'purpose': 'independent_sft_source_group_holdout', 'expected_training_input_sha256': train_sha,
                'unseen_by_legacy_cpt': False, 'test_used_for_selection': False})
    artifacts = []
    for kind, root, name in (('diagnostics', diag, 'bkquiz_schema_diagnostics_input.zip'), ('train', train, 'bkquiz_sft_v2_train_input.zip'), ('test', test, 'bkquiz_sft_v2_test100_input.zip')):
        manifest = load(root/'manifest.json')
        archive = RELEASE/name
        make_zip(archive, {n: root/n for n in ['manifest.json', *manifest['files_sha256']]})
        nb_name, nb = notebook(kind, name, sha(archive)); save(RELEASE/nb_name, nb)
        artifacts.append({'kind': kind, 'archive': str(archive), 'archive_sha256': sha(archive), 'size_bytes': archive.stat().st_size,
                          'notebook': str(RELEASE/nb_name), 'notebook_sha256': sha(RELEASE/nb_name)})
    report = {'release': str(RELEASE), 'drive_folder': DRIVE_FOLDER, 'artifacts': artifacts,
              'training_counts': {'theory_to_quiz': 243, 'source_qa': 14, 'mcq_format': 13, 'validation_quiz': 30},
              'test_references': 100, 'gpu_executed_by_codex': False, 'expert_semantically_verified': False,
              'scope': 'controlled_concept_discrimination_pilot_from_native_theory; not unrestricted_deep_scenario_generation'}
    save(RELEASE/'COLAB_HANDOFF.json', report); print(canonical(report).decode(), flush=True)
    return report


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8'); build()
