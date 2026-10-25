"""Publish a separately named 14-input recovery release and an in-place Colab cell."""
import copy
from pathlib import Path
import shutil

from common import atomic_json,digest,load
from build_notebook import build

ROOT=Path(__file__).resolve().parent
REVISION='l4-empty-batch-fix-20261022'
RUNTIME_NAME='colab_orchestrator_v3_l4_batchfix_runtime.zip'
NOTEBOOK_NAME='Colab_V5_L4_Resume14_BatchFix.ipynb'


def publish():
    nb=load(build());release=load(ROOT/'RUNTIME_RELEASE.json')
    shutil.copyfile(ROOT/release['runtime_zip'],ROOT/RUNTIME_NAME)
    fixed=copy.deepcopy(nb)
    for c in fixed['cells']:
        text=''.join(c['source']).replace(release['runtime_zip'],RUNTIME_NAME).replace('l4-stability-20261022',REVISION)
        if c['cell_type']=='markdown' and text.startswith('# BKQuiz'):
            text='# BKQuiz v5 — tiếp tục 14 input L4, sửa checkpoint không có output\n'+text.split('\n',1)[1]
            text+='\nGiữ BASE v3 cũ để tiếp tục input chưa commit. Checkpoint Docling lỗi không có output được khôi phục như một lỗi; không tự coi là thành công.\n'
        c['source']=text.splitlines(True)
    fixed['metadata']['colab']['name']=NOTEBOOK_NAME;fixed['metadata']['bkquiz_runtime']['revision']=REVISION
    atomic_json(ROOT/NOTEBOOK_NAME,fixed)
    fixed_release={**release,'runtime_zip':RUNTIME_NAME,'runtime_zip_sha256':digest(ROOT/RUNTIME_NAME),
                   'runtime_revision':REVISION,'notebook':NOTEBOOK_NAME,'actual_Colab_recovery_executed':False}
    atomic_json(ROOT/'BATCHFIX_RELEASE.json',fixed_release)
    cell='''# Chép toàn bộ nội dung này vào một cell mới của notebook 14 input hiện tại.
# Trước đó upload colab_orchestrator_v3_l4_batchfix_runtime.zip vào MyDrive/BKQuiz_cpt_data.
# Không cần restart VM/cài lại venv nếu phiên hiện tại còn hoạt động.
from pathlib import Path
import hashlib, importlib.util, json, os, sys, zipfile
'''
    cell+='FIX_SHA256='+repr(fixed_release['runtime_zip_sha256'])+'\nFIX_FILES='+repr(fixed_release['files'])+'\n'
    cell+='FIX_REVISION='+repr(REVISION)+'\n'
    cell+='''FIX_BASE=Path(globals().get('BASE','/content/drive/MyDrive/BKQuiz_v5_drive_v3'))
FIX_WORK=Path(globals().get('WORK','/content/bkquiz_v5_drive_v3'))
FIX_INPUT_DIR=Path(globals().get('INPUT_DIR','/content/drive/MyDrive/BKQuiz_cpt_data'))
FIX_ZIP=FIX_INPUT_DIR/'colab_orchestrator_v3_l4_batchfix_runtime.zip'
FIX_RUNTIME=Path('/content/bkquiz_v5_drive_v3_batchfix_runtime')
def fix_load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def fix_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
assert fix_sha(FIX_ZIP)==FIX_SHA256,'Sai runtime ZIP; dùng đúng bản batchfix'
FIX_RUNTIME.mkdir(exist_ok=True)
with zipfile.ZipFile(FIX_ZIP) as z:
    assert len(z.namelist())==len(set(z.namelist()))
    assert set(z.namelist())==set(FIX_FILES)|{'runtime.json'}
    for name,wanted in FIX_FILES.items():
        assert Path(name).name==name
        data=z.read(name);assert hashlib.sha256(data).hexdigest()==wanted,name
        (FIX_RUNTIME/name).write_bytes(data)
fix_state=fix_load(FIX_BASE/'queue_state.json')
assert fix_state['schema']=='v5-orchestrator-3-drive','Đây là bản tiếp tục queue v3 / 14 input'
print('Input đã commit:',fix_state.get('last_acknowledged_index',0))
for key,item in fix_state.get('page_batches',{}).items():
    if hashlib.sha256(key.encode()).hexdigest()[:20]=='53296f7b00c115de9162':
        print('Checkpoint liên quan:',key)
        response=item.get('response',{})
        print('Phản hồi Docling gốc:',response)
        with zipfile.ZipFile(item['archive']) as z:
            m=json.loads(z.read('batch.json'))
            print('Số file output trong checkpoint:',sum(n.startswith('output/') for n in m['files']))
        break
FIX_ENVS=fix_load(FIX_BASE/'environments.json')
assert Path(FIX_ENVS['controller']).exists(),'Venv không còn: dùng notebook Resume14_BatchFix để khôi phục môi trường'
fix_old_session=globals().get('SESSION')
FIX_KEEP_MODEL=getattr(fix_old_session,'keep_model',globals().get('KEEP_MODEL_RESIDENT',True))
FIX_BATCH_PAGES=fix_state.get('batch_pages',globals().get('BATCH_PAGES',20))
if fix_old_session is not None and fix_old_session.process.poll() is None and getattr(fix_old_session,'runtime_revision',None)==FIX_REVISION:
    SESSION=fix_old_session
else:
    if fix_old_session is not None and fix_old_session.process.poll() is None:
        fix_old_session.close()  # Chỉ đóng controller/model của phiên này, giữ venv và mọi file Drive.
    os.environ['BKQUIZ_RUNTIME_REVISION']=FIX_REVISION
    os.environ.setdefault('BKQUIZ_DOCLING_HF_HOME',str(FIX_BASE/'docling_hf_cache_l4'))
    spec=importlib.util.spec_from_file_location('_bkquiz_batchfix_client',FIX_RUNTIME/'client.py')
    fix_client=importlib.util.module_from_spec(spec);spec.loader.exec_module(fix_client)
    SESSION=fix_client.Session(FIX_ENVS['controller'],FIX_BASE,keep_model=FIX_KEEP_MODEL,batch_pages=FIX_BATCH_PAGES,work=FIX_WORK)
FIX_INPUTS=globals().get('INPUTS')
if not FIX_INPUTS:
    FIX_INPUTS=[]
    for path in sorted(FIX_INPUT_DIR.rglob('*.zip')):
        with zipfile.ZipFile(path) as z:
            if 'bundle.json' not in z.namelist():continue
            m=json.loads(z.read('bundle.json'))
        if m.get('schema')=='v5-orchestrator-2-sequential' and m.get('sequence_required'):
            FIX_INPUTS.append({'path':str(path),'manifest':m})
    FIX_INPUTS.sort(key=lambda x:x['manifest']['bundle_index'])
assert len(FIX_INPUTS)==14,'Cần đúng bộ 14 input hiện tại'
fix_expected=fix_load(FIX_BASE/'queue_state.json').get('last_acknowledged_index',0)+1
if fix_expected<=14:
    fix_selected=next(x for x in FIX_INPUTS if x['manifest']['bundle_index']==fix_expected)
    print('TIẾP TỤC INPUT',fix_expected,'/ 14',flush=True)
    RESULT=SESSION.process_input(fix_selected['path'])
    SESSION.commit(RESULT)
    print('ĐÃ LƯU KẾT QUẢ:',RESULT['archive'])
    print('SHA256:',RESULT['archive_sha256'])
    print('Chất lượng:',RESULT['summary'])
    print('Chạy lại cell này để tiếp tục input kế tiếp; không chạy lại bootstrap cũ.')
else:
    print('Đã commit đủ 14 input.');SESSION.close()
'''
    compile(cell,'colab_recovery_cell','exec')
    (ROOT/'COLAB_RESUME_INPUT7_CELL.txt').write_text(cell,encoding='utf-8')
    return fixed_release


if __name__=='__main__':print(publish()['notebook'])
