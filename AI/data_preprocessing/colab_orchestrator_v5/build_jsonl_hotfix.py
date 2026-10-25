"""Build a copyable surgical Colab repair cell, preserving user crop fixes."""
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REVISION = 'v6-jsonl-unicode-l4-20261023'


def apply_hotfix(runtime, base, adapter_source):
    import hashlib
    import json
    import os
    from pathlib import Path
    import time

    runtime, base = Path(runtime).resolve(), Path(base).resolve()
    if not (runtime/'client.py').is_file() or not (runtime/'unit_queue.py').is_file():
        raise RuntimeError('Không tìm thấy runtime 134 gói; chạy các cell cấu hình trước.')
    # Exact anchors only. Unexpected local edits are retained and reported.
    replacements = {
        'common.py': [("def rows(path):\n    with Path(path).open(encoding='utf-8-sig') as f:\n        return [json.loads(line) for line in f if line.strip()]",
                       "def rows(path):\n    from jsonl_adapter import read_jsonl\n    return read_jsonl(path)")],
        'unit_store.py': [
            ('from common import atomic_json,copy_verified,digest,load,safe',
             'from common import atomic_json,copy_verified,digest,load,safe\nfrom jsonl_adapter import loads_jsonl'),
            ("def json_rows(name):return [json.loads(line) for line in read_logical(name).splitlines() if line.strip()]",
             "def json_rows(name):return loads_jsonl(read_logical(name),str(path)+'!'+name)")],
        'unit_queue.py': [('        io_utils.file_sha=digest\n',
                           '        io_utils.file_sha=digest\n        from jsonl_adapter import install as install_jsonl\n        install_jsonl()\n')],
        'stage_worker.py': [('    io_utils.file_sha=digest\n',
                             '    io_utils.file_sha=digest\n    from jsonl_adapter import install as install_jsonl\n    install_jsonl()\n')],
        'warm_worker.py': [('    io_utils.file_sha = digest  # Streaming hash adapter; frozen files remain unchanged.\n',
                            '    io_utils.file_sha = digest  # Streaming hash adapter; frozen files remain unchanged.\n    from jsonl_adapter import install as install_jsonl\n    install_jsonl()\n')],
        'runtime_profile.py': [('    io_utils.file_sha=digest\n',
                                '    io_utils.file_sha=digest\n    from jsonl_adapter import install as install_jsonl\n    install_jsonl()\n')],
        'import_units.py': [('    verify_release(ENGINE);sys.path.insert(0,str(ENGINE))\n',
                             '    verify_release(ENGINE);sys.path.insert(0,str(ENGINE))\n    from jsonl_adapter import install as install_jsonl\n    install_jsonl()\n')],
    }
    pending = {}
    for name, pairs in replacements.items():
        path = runtime/name
        text = path.read_text(encoding='utf-8-sig')
        for old, new in pairs:
            if new in text:
                continue
            if text.count(old) != 1:
                raise RuntimeError('Runtime đã đổi tại '+name+'; chưa sửa file nào. Dùng notebook/runtime JSONL Fix mới.')
            text = text.replace(old, new, 1)
        compile(text, str(path), 'exec')
        pending[path] = text.encode('utf-8')
    compile(adapter_source, 'jsonl_adapter.py', 'exec')
    pending[runtime/'jsonl_adapter.py'] = adapter_source.encode('utf-8')
    # Validate the actual helper source before making any changes.
    namespace = {'__name__':'jsonl_hotfix_self_test'}
    exec(compile(adapter_source, 'jsonl_adapter.py', 'exec'), namespace)
    assert namespace['loads_jsonl']('{"text":"x\u2028y\u0085z\u2029; ≤ 2"}\n') == [{'text':'x\u2028y\u0085z\u2029; ≤ 2'}]
    stamp = str(time.time_ns())
    backup = base/'runtime_hotfixes'/('jsonl_20261023_'+stamp)
    backup.mkdir(parents=True, exist_ok=False)
    originals = {p:p.read_bytes() if p.exists() else None for p in pending}
    before = {}
    # Back up the whole runtime, including any user edits to native_batches.py.
    for path in runtime.glob('*.py'):
        data = path.read_bytes(); target = backup/path.name; target.write_bytes(data)
        wanted = hashlib.sha256(data).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != wanted:
            raise RuntimeError('Sao lưu runtime không khớp hash; chưa sửa file nào.')
        before[path.name] = wanted
    try:
        for path, data in pending.items():
            temporary = path.with_name(path.name+'.jsonl_fix.next')
            temporary.write_bytes(data); os.replace(temporary, path)
        result = {'revision':'v6-jsonl-unicode-l4-20261023', 'backup':str(backup), 'runtime':str(runtime),
                  'before':before, 'patched':{p.name:hashlib.sha256(data).hexdigest() for p,data in pending.items()},
                  'source_core_modified':False, 'records_modified':False, 'receipts_modified':False,
                  'native_batches_modified':False, 'unix':time.time()}
        (backup/'hotfix_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    except BaseException:
        for path, data in originals.items():
            if data is None:
                if path.exists():path.unlink()
            else:path.write_bytes(data)
        raise
    return result


def build():
    source = '''# Chạy sau khi cell lỗi đã dừng. Dùng lại venv, input, BASE và kết quả đã lưu.
import os
from pathlib import Path
import client
required = ['BASE', 'WORK', 'ENVS', 'INDEX', 'PROFILE', 'DOC_HF_HOME', 'KEEP_MODEL_RESIDENT']
assert all(name in globals() for name in required), 'Chạy các cell cấu hình trước.'
'''
    source += '\n'+inspect.getsource(apply_hotfix)+'\n'
    source += 'ADAPTER_SOURCE = '+repr((ROOT/'jsonl_adapter.py').read_text(encoding='utf-8'))+'\n'
    source += '''# Đóng riêng controller/model worker; không xóa môi trường hoặc kết quả Drive.
if globals().get('SESSION') is not None:
    SESSION.close()
globals().pop('SESSION', None)
HOTFIX = apply_hotfix(Path(client.__file__).resolve().parent, BASE, ADAPTER_SOURCE)
os.environ['BKQUIZ_RUNTIME_REVISION'] = HOTFIX['revision']
# Chặn cell nạp runtime cũ ghi đè bản vá trong kernel này.
_UNIT_RUNTIME_SHA = 'hotfix:' + HOTFIX['revision']
print('ĐÃ VÁ JSONL:', HOTFIX['revision'])
print('Sao lưu runtime trước vá:', HOTFIX['backup'])
print('Giữ nguyên venv, native_batches.py, PDF, bản ghi và ZIP/receipt trên Drive.')
print('Chạy cell COLAB_AUTO_SKIP_CELL.txt mới để quét lại ZIP và xử lý gói thiếu.')
print('Nếu gói 61 từng bị auto-skip: đặt RETRY_FAILED=True trong cell xử lý để thử lại.')
print('Không chạy lại cell 2 của notebook cũ; khi đổi VM hãy dùng notebook JSONL Fix mới.')
'''
    compile(source, 'COLAB_JSONL_REPAIR_CELL', 'exec')
    path = ROOT/'COLAB_JSONL_REPAIR_CELL.txt'
    path.write_text(source,encoding='utf-8')
    resume = source.replace(
        "print('Chạy cell COLAB_AUTO_SKIP_CELL.txt mới để quét lại ZIP và xử lý gói thiếu.')",
        "print('Đang quét lại ZIP và tiếp tục các gói còn thiếu; gói lỗi được thử lại một lần trong lượt này.')")
    resume += "\nMAX_UNITS = globals().get('MAX_UNITS', None)\n"
    resume += (ROOT/'COLAB_AUTO_SKIP_CELL.txt').read_text(encoding='utf-8').replace('RETRY_FAILED = False','RETRY_FAILED = True')
    compile(resume, 'COLAB_JSONL_REPAIR_AND_RESUME', 'exec')
    (ROOT/'COLAB_JSONL_REPAIR_AND_RESUME.txt').write_text(resume,encoding='utf-8')
    return path


if __name__ == '__main__': print(build())
