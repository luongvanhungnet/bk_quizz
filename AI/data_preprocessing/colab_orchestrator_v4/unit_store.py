"""Only complete, hash-verified Drive ZIPs count as completed units."""
import hashlib
import json
from pathlib import Path
import stat
import time
import zipfile
import zlib

from common import atomic_json,copy_verified,digest,load,safe

INPUT_SCHEMA='v5-unit-input-v1'
RESULT_SCHEMA='v5-unit-result-v1'


def read_index(folder):
    folder=Path(folder);index=load(folder/'UPLOAD_INDEX.json')
    if index.get('schema')!=INPUT_SCHEMA:raise ValueError('Use the independent 100-page inputs')
    entries=index['bundles']
    if len(entries)!=index['bundle_count'] or len({e['unit_id'] for e in entries})!=len(entries):raise ValueError('Duplicate/missing unit IDs')
    if [e['bundle_index'] for e in entries]!=list(range(1,len(entries)+1)):raise ValueError('Invalid unit indices')
    seen=set()
    for e in entries:
        if e['unit_id']!=f'unit_{e["bundle_index"]:04d}':raise ValueError('Invalid unit ID')
        if not 0<e['pages']<=100:raise ValueError('A unit must contain 1..100 processing pages')
        path=safe(folder,e['filename'])
        if path.parent!=folder.resolve() or path.suffix!='.zip':raise ValueError('Invalid input filename')
        refs=[(r['source_sha256'],p) for r in e['source_ranges'] for p in range(r['first_page'],r['last_page']+1)]
        if len(refs)!=e['pages'] or len(set(refs))!=len(refs) or seen.intersection(refs):raise ValueError('Duplicate/missing page scope')
        seen.update(refs);e['path']=str(path)
    if len(seen)!=index['pages']:raise ValueError('Corpus page count mismatch')
    return index


def ranges(entry):
    return sorted((r['document_id'],r['source_sha256'],r['first_page'],r['last_page']) for r in entry['source_ranges'])


def inspect_result(path,entry,plan_sha,*,members=True):
    """Inspect data without materializing it; never accept partial/diagnostic ZIPs."""
    path=Path(path)
    if path.suffix!='.zip':raise ValueError('Only final .zip files can be completed')
    with zipfile.ZipFile(path) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        if len(set(names))!=len(names):raise ValueError('Duplicate ZIP entries')
        for i in infos:
            safe(Path('/unit_validation'),i.filename)
            if stat.S_ISLNK(i.external_attr>>16):raise ValueError('ZIP symlinks rejected')
            if i.flag_bits&1:raise ValueError('Encrypted result ZIP entries rejected')
        if sum(i.file_size for i in infos)>32*1024**3:raise ValueError('Result exceeds uncompressed size limit')
        m=json.loads(z.read('return.json'))
        if (m.get('schema')!=RESULT_SCHEMA or m.get('unit_id')!=entry['unit_id'] or m.get('plan_sha256')!=plan_sha
            or m.get('input_sha256')!=entry['sha256'] or m.get('pages')!=entry['pages']
            or ranges(m)!=ranges(entry) or m.get('processing_complete') is not True
            or m.get('diagnostic_only') or m.get('training_exported') or m.get('human_verified') or m.get('semantic_verified')):
            raise ValueError('Result identity/completion gate failed')
        expected=m['files'];logical=m['logical_files']
        if set(names)!=set(expected)|{'return.json'} or set(expected)!={'objects/'+h for h in logical.values()}:
            raise ValueError('Result object inventory mismatch')
        for name,sha in logical.items():
            safe(Path('/unit_validation'),name)
            if '.sqlite' in name or name.startswith('objects/') or name=='return.json':raise ValueError('Reserved/human-review file in result')
            if expected['objects/'+sha]!=sha:raise ValueError('Object hash/path mismatch')
        if members:
            for name,wanted in expected.items():
                h=hashlib.sha256()
                with z.open(name) as source:
                    for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
                if h.hexdigest()!=wanted:raise ValueError('Result member changed: '+name)
            def read_logical(name):return z.read('objects/'+logical[name]).decode('utf-8-sig')
            def json_rows(name):return [json.loads(line) for line in read_logical(name).splitlines() if line.strip()]
            if not m.get('summary',{}).get('all_jobs_executed'):raise ValueError('Missing executed-job evidence')
            wanted_docs={r['document_id'] for r in entry['source_ranges']}
            if set(m.get('runs',[]))!=wanted_docs:raise ValueError('Missing result run')
            for scope in entry['source_ranges']:
                prefix='runs/'+scope['document_id']+'/'
                manifest=json.loads(read_logical(prefix+'manifest.json'))
                if manifest['document']['sha256']!=scope['source_sha256']:raise ValueError('Run source mismatch')
                pages=json_rows(prefix+'document_pages.jsonl')
                wanted=set(range(scope['first_page'],scope['last_page']+1))
                if len(pages)!=len(wanted) or {p['page'] for p in pages}!=wanted:raise ValueError('Incomplete/extra result pages')
                records=json_rows(prefix+'records.jsonl')
                if {r['page'] for r in records}!=wanted or len({r['id'] for r in records})!=len(records):
                    raise ValueError('Incomplete/duplicate region records')
                for r in records:
                    if r['source_sha256']!=scope['source_sha256'] or r.get('human_verified') or r.get('semantic_verified'):
                        raise ValueError('Invalid machine record provenance/verification')
                    for field in ['crop','context','render']:
                        if logical[prefix+r[field+'_path']]!=r[field+'_sha256']:raise ValueError('Region asset mismatch')
    return m


class UnitStore:
    def __init__(self,base,index):
        self.base=Path(base);self.index=index
        self.entries={e['unit_id']:e for e in index['bundles']};self.completed={}
        self.base.mkdir(parents=True,exist_ok=True)
        identity=self.base/'unit_queue_identity.json'
        wanted={'schema':INPUT_SCHEMA,'plan_sha256':index['plan_sha256'],'units':index['bundle_count'],'pages':index['pages']}
        if identity.exists() and load(identity)!=wanted:raise ValueError('BASE belongs to a different unit plan')
        if not identity.exists():atomic_json(identity,wanted)

    def receipt_path(self,unit_id):return self.base/'receipts'/(unit_id+'.json')

    def remember(self,entry,path,sha,*,recovered=False):
        value={'schema':RESULT_SCHEMA,'status':'complete','unit_id':entry['unit_id'],
               'plan_sha256':self.index['plan_sha256'],'input_sha256':entry['sha256'],'pages':entry['pages'],
               'archive':str(Path(path)),'archive_sha256':sha,'archive_bytes':Path(path).stat().st_size,
               'drive_saved_verified':True,'recovered_orphan_zip':recovered,'saved_unix':time.time()}
        previous=self.receipt_path(entry['unit_id'])
        if previous.exists():
            atomic_json(self.base/'receipts/history'/(entry['unit_id']+'_'+str(time.time_ns())+'.json'),load(previous))
        atomic_json(previous,value);self.completed[entry['unit_id']]=value
        return value

    def scan(self):
        """Reconcile holes, bad receipts, missing ZIPs and ZIP-before-receipt crashes."""
        self.completed={};issues=[]
        for number,entry in enumerate(self.index['bundles'],1):
            uid=entry['unit_id'];receipt=self.receipt_path(uid)
            if receipt.exists():
                try:
                    r=load(receipt);path=Path(r['archive']).resolve()
                    if not path.is_relative_to((self.base/'results'/uid).resolve()):raise ValueError('Result outside unit result directory')
                    if (r.get('status')!='complete' or not r.get('drive_saved_verified') or r.get('unit_id')!=uid
                        or r.get('plan_sha256')!=self.index['plan_sha256'] or r.get('input_sha256')!=entry['sha256']):
                        raise ValueError('Receipt not complete or identity changed')
                    if path.stat().st_size!=r['archive_bytes'] or digest(path)!=r['archive_sha256']:raise ValueError('Saved result missing/corrupted')
                    inspect_result(path,entry,self.index['plan_sha256'],members=False)
                    self.completed[uid]=r
                except (OSError,ValueError,KeyError,TypeError,RuntimeError,zipfile.BadZipFile,zlib.error) as exc:
                    issues.append({'unit_id':uid,'receipt':str(receipt),'error':repr(exc)})
            if uid not in self.completed:
                for path in sorted((self.base/'results'/uid).glob('*.zip'),reverse=True):
                    try:
                        inspect_result(path,entry,self.index['plan_sha256'])
                        self.remember(entry,path,digest(path),recovered=True);break
                    except (OSError,ValueError,KeyError,TypeError,RuntimeError,zipfile.BadZipFile,zlib.error) as exc:
                        issues.append({'unit_id':uid,'archive':str(path),'error':repr(exc)})
            if number%10==0 or number==len(self.entries):
                print(f'CHECK SAVED {number}/{len(self.entries)}: {len(self.completed)} complete ZIPs verified',flush=True)
        atomic_json(self.base/'reconciliation_issues.json',issues)
        return self.summary()

    def summary(self):
        pending=[e['unit_id'] for e in self.index['bundles'] if e['unit_id'] not in self.completed]
        return {'schema':RESULT_SCHEMA,'total_units':len(self.entries),'completed_units':len(self.completed),
                'completed_pages':sum(self.entries[u]['pages'] for u in self.completed),'pending_units':pending,
                'next_unit':pending[0] if pending else None,'updated_unix':time.time()}

    def pending(self):return [e for e in self.index['bundles'] if e['unit_id'] not in self.completed]

    def publish(self,local,entry):
        inspect_result(local,entry,self.index['plan_sha256'])
        sha=digest(local);target=self.base/'results'/entry['unit_id']/(str(time.time_ns())+'_'+sha[:12]+'.zip')
        copied=copy_verified(local,target,expected_sha256=sha)
        # copy_verified has read back the Drive destination before this receipt.
        r=self.remember(entry,target,copied['sha256']);atomic_json(self.base/'queue_state.json',self.summary())
        print('SAVED',entry['unit_id'],str(target),flush=True)
        return r
