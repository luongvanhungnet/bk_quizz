"""Run independent parsers in their own environments; preserve raw files and mapping."""
import argparse
from pathlib import Path
import zipfile
from io_utils import load,file_sha,write_once,safe_path
from adapters import run_docling,run_mineru,import_docling,import_mineru

def run(packet,out,engine):
    packet=Path(packet);out=Path(out);m=load(packet/'manifest.json');pdf=safe_path(packet,m['parser_input'])
    if file_sha(pdf)!=m['parser_input_sha256']:raise ValueError('Changed independent parser input')
    out.mkdir(parents=True,exist_ok=True);candidates=[]
    if engine=='docling':
        raw=out/'docling_raw.json';status=run_docling(pdf,raw,do_ocr=False)
        if status['status']=='ok':candidates=import_docling(raw)
    else:
        status=run_mineru(pdf,out/'mineru_raw',executable='mineru-kit',backend='standard')
        if status['status']=='ok':
            paths=list((out/'mineru_raw').rglob('*.json'))
            for archive in (out/'mineru_raw').rglob('*.zip'):
                with zipfile.ZipFile(archive) as z:
                    if z.testzip():raise ValueError('Corrupt MinerU ZIP')
                    for info in z.infolist():
                        if not info.filename.endswith('.json'):continue
                        destination=safe_path(out/'mineru_materialized',info.filename);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(z.read(info.filename));paths.append(destination)
            for path in paths:
                if path.name in ['run.json']:continue
                try:items=import_mineru(path)
                except (ValueError,KeyError,TypeError):continue
                if items:candidates+=items
    result={'engine':engine,'status':status['status'],'original_source_sha256':m['document']['sha256'],
        'parser_input_sha256':m['parser_input_sha256'],'packet_manifest_sha256':file_sha(packet/'manifest.json'),
        'parser_candidates':candidates,'semantic_verified':False,'raw_status':{k:v for k,v in status.items() if k!='document'}}
    write_once(out/('parser_candidates_'+engine+'.json'),result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--engine',choices=['docling','mineru'],required=True)
    a=p.parse_args();print(run(a.input,a.out,a.engine)['status'])
