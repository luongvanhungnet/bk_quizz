"""Generate an in-place cell for the existing 14-input queue; never rebuild its runtime."""
from pathlib import Path
import json
import hashlib

ROOT = Path(__file__).resolve().parent


def build():
    release = json.loads((ROOT / 'BATCHFIX_RELEASE.json').read_text(encoding='utf-8'))
    archive = ROOT / release['runtime_zip']
    if hashlib.sha256(archive.read_bytes()).hexdigest() != release['runtime_zip_sha256']:
        raise ValueError('Batchfix release/archive mismatch')
    cell = '''# Thay cell xử lý cũ bằng cell này, sau khi cell cũ đã dừng.
# Đặt runtime ZIP batchfix trong MyDrive/BKQuiz_cpt_data; giữ nguyên BASE và các input cũ.
from pathlib import Path
import hashlib, importlib.util, json, os, sys, zipfile

'''
    cell += 'FIX_ZIP_NAME = ' + repr(release['runtime_zip']) + '\n'
    cell += 'FIX_SHA256 = ' + repr(release['runtime_zip_sha256']) + '\n'
    cell += 'FIX_REVISION = ' + repr(release['runtime_revision']) + '\n'
    cell += '''
def resume_inputs_10_14():
    global SESSION, RESULT
    base = Path(globals().get('BASE', '/content/drive/MyDrive/BKQuiz_v5_drive_v3'))
    work = Path(globals().get('WORK', '/content/bkquiz_v5_drive_v3'))
    input_dir = Path(globals().get('INPUT_DIR', '/content/drive/MyDrive/BKQuiz_cpt_data'))

    def read_json(path):
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))

    def file_sha(path):
        h = hashlib.sha256()
        with Path(path).open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                h.update(block)
        return h.hexdigest()

    state = read_json(base / 'queue_state.json')
    if state.get('schema') != 'v5-orchestrator-3-drive':
        raise RuntimeError('Sai BASE: cell này chỉ dành cho queue v3 / 14 input hiện tại.')
    acknowledged = state.get('last_acknowledged_index', 0)
    if not isinstance(acknowledged, int) or not 9 <= acknowledged <= 14:
        raise RuntimeError(f'State đang ở {acknowledged}/14. Cần commit đủ input 1–9; không sửa số tiến độ thủ công.')
    print('Đã commit trên Drive:', acknowledged, '/14', flush=True)
    if acknowledged == 14:
        print('Đã lưu đủ kết quả đến input 14.'); return

    # Chọn theo manifest, không dùng vị trí INPUTS và không ghi đè tiến độ.
    paths = {}
    for index in range(acknowledged + 1, 15):
        path = input_dir / f'v5_sequential_{index:02d}_of_14.zip'
        with zipfile.ZipFile(path) as z:
            m = json.loads(z.read('bundle.json'))
        if not (m.get('schema') == 'v5-orchestrator-2-sequential'
                and m.get('sequence_required') is True and m.get('bundle_count') == 14
                and m.get('bundle_index') == index and m.get('plan_sha256') == state.get('plan_sha256')):
            raise RuntimeError(f'Input sai thứ tự hoặc khác kế hoạch: {path}')
        paths[index] = path

    archive = input_dir / FIX_ZIP_NAME
    if file_sha(archive) != FIX_SHA256:
        raise RuntimeError('Sai runtime ZIP. Upload đúng file batchfix đi kèm cell này.')
    runtime = work.parent / ('bkquiz_v5_batchfix_' + FIX_SHA256[:12])
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        files = json.loads(z.read('runtime.json'))['files']
        if len(names) != len(set(names)) or set(names) != set(files) | {'runtime.json'}:
            raise RuntimeError('Inventory runtime không hợp lệ.')
        runtime.mkdir(parents=True, exist_ok=True)
        for name, wanted in files.items():
            data = z.read(name)
            if Path(name).name != name or hashlib.sha256(data).hexdigest() != wanted:
                raise RuntimeError('Runtime hash không hợp lệ: ' + name)
            (runtime / name).write_bytes(data)

    envs = read_json(base / 'environments.json')
    if not Path(envs['controller']).is_file():
        raise RuntimeError('Venv đã mất. Chạy phần khôi phục môi trường trong notebook BatchFix trước.')
    batch_pages = state['batch_pages']  # Giữ kích thước checkpoint đã lưu.
    old = globals().get('SESSION')
    keep_model = globals().get('KEEP_MODEL_RESIDENT', getattr(old, 'keep_model', True))
    profile = globals().get('PROFILE', 'l4-highram-python3-20261021')
    doc_home = str(globals().get('DOC_HF_HOME', base / 'docling_hf_cache_l4'))
    reuse = (old is not None and old.process.poll() is None
             and getattr(old, 'runtime_revision', None) == FIX_REVISION
             and getattr(old, 'runtime_profile', None) == profile
             and getattr(old, 'docling_hf_home', None) == doc_home
             and getattr(old, 'batch_pages', None) == batch_pages
             and getattr(old, 'keep_model', None) == keep_model
             and Path(str(getattr(old, 'base', ''))) == base
             and Path(str(getattr(old, 'work', ''))) == work)
    if not reuse:
        if old is not None and old.process.poll() is None:
            print('Đóng controller cũ; giữ venv và checkpoint Drive.', flush=True)
            old.close()
        os.environ.update(BKQUIZ_RUNTIME_REVISION=FIX_REVISION,
                          BKQUIZ_RUNTIME_PROFILE=profile, BKQUIZ_DOCLING_HF_HOME=doc_home)
        # Import client riêng, tránh dùng class Session cũ còn trong kernel.
        sys.path.insert(0, str(runtime))
        try:
            spec = importlib.util.spec_from_file_location('_bkquiz_range_client', runtime / 'client.py')
            client = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(client)
        finally:
            sys.path.pop(0)
        SESSION = client.Session(envs['controller'], base, keep_model=keep_model,
                                 batch_pages=batch_pages, work=work)

    for index in range(acknowledged + 1, 15):
        current = read_json(base / 'queue_state.json')
        if current.get('last_acknowledged_index') != index - 1:
            raise RuntimeError('Tiến độ đã thay đổi. Không chạy hai queue cùng BASE; kiểm tra rồi chạy lại cell.')
        print(f'INPUT {index}/14: {paths[index]}', flush=True)
        try:
            RESULT = SESSION.process_input(paths[index])
            if RESULT.get('bundle_index') != index or not RESULT.get('summary', {}).get('all_jobs_executed'):
                raise RuntimeError('Kết quả chưa hoàn chỉnh; không commit input này.')
            SESSION.commit(RESULT)  # Controller kiểm hash ZIP Drive trước khi commit.
        except Exception:
            print(f'Dừng tại input {index}; giữ checkpoint và các gói đã commit. Chạy lại cell để tiếp tục.', flush=True)
            raise
        print('ĐÃ LƯU DRIVE:', RESULT['archive'], flush=True)
        print('SHA256:', RESULT['archive_sha256'], flush=True)
        print('Chất lượng:', RESULT['summary'], flush=True)
    SESSION.close()
    print('Đã lưu và commit đủ kết quả đến input 14/14.', flush=True)

resume_inputs_10_14()
'''
    compile(cell, 'COLAB_RESUME_10_14_CELL', 'exec')
    target = ROOT / 'COLAB_RESUME_10_14_CELL.txt'
    target.write_text(cell, encoding='utf-8')
    return target


if __name__ == '__main__':
    print(build())
