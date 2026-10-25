"""Local page slices with explicit mappings back to an immutable parent packet."""
import copy
import gc
import os
from pathlib import Path
import shutil

from common import atomic_json, digest, load, safe


def split_packet(packet, root, batch_pages=20):
    import pymupdf
    if batch_pages < 1: raise ValueError('batch_pages must be positive')
    packet, root = Path(packet), Path(root)
    m=load(packet/'manifest.json'); pages=sorted(m['page_map'].values())
    parent_indices={page:int(index)-1 for index,page in m['page_map'].items()}
    with pymupdf.open(safe(packet,m['parser_input'])) as pdf:
        for offset in range(0,len(pages),batch_pages):
            selected=pages[offset:offset+batch_pages]
            folder=root/f'{selected[0]:05d}-{selected[-1]:05d}'
            if (folder/'manifest.json').exists():
                child=load(folder/'manifest.json')
                if child.get('parent_packet_manifest_sha256')!=digest(packet/'manifest.json'):
                    raise ValueError('Parent batch packet changed')
                yield folder
                continue
            folder.mkdir(parents=True,exist_ok=True)
            child=copy.deepcopy(m);child['requests']=[q for q in child['requests'] if q['page'] in selected]
            child['page_map']={str(i+1):page for i,page in enumerate(selected)}
            child['parent_packet_manifest_sha256']=digest(packet/'manifest.json')
            child['parent_parser_input_sha256']=m['parser_input_sha256']
            for name in set(m['code_sha256']) | {q[k] for q in child['requests'] for k in ['image','vlm_image']}:
                dest=safe(folder,name);dest.parent.mkdir(parents=True,exist_ok=True)
                if not dest.exists():
                    try:os.link(safe(packet,name),dest)
                    except OSError:shutil.copyfile(safe(packet,name),dest)
            subset=pymupdf.open()
            try:
                for page in selected:subset.insert_pdf(pdf,from_page=parent_indices[page],to_page=parent_indices[page])
                subset.save(folder/m['parser_input'],garbage=4,deflate=True)
            finally:subset.close()
            child['parser_input_sha256']=digest(folder/m['parser_input'])
            atomic_json(folder/'manifest.json',child)
            yield folder
            gc.collect()


def normalized_files(parent, child, out, role):
    """Write ingestion envelopes; original raw outputs remain unchanged for audit."""
    parent,child,out=Path(parent),Path(child),Path(out)
    pm,cm=load(parent/'manifest.json'),load(child/'manifest.json')
    parent_sha=digest(parent/'manifest.json');child_sha=digest(child/'manifest.json')
    parent_index={page:int(index) for index,page in pm['page_map'].items()}
    result={}
    if role not in {'vlm','docling'}:
        for p in (out/'records').glob('*.json'):
            result[f'paddle_{role}/records/{child.name}_{p.name}']=p
    elif role=='vlm':
        for p in out.glob('vlm_results_*.json'):
            payload=load(p)
            if payload['packet_manifest_sha256']!=child_sha:raise ValueError('VLM child packet identity mismatch')
            payload['child_packet_manifest_sha256']=child_sha
            payload['packet_manifest_sha256']=parent_sha
            target=out/'normalized'/p.name;atomic_json(target,payload)
            result[f'vlm/{child.name}_{p.name}']=target
    else:
        for p in out.glob('parser_candidates_*.json'):
            payload=load(p)
            if payload['packet_manifest_sha256']!=child_sha or payload['parser_input_sha256']!=cm['parser_input_sha256']:
                raise ValueError('Parser child identity mismatch')
            payload.update(child_packet_manifest_sha256=child_sha,child_parser_input_sha256=cm['parser_input_sha256'],
                           packet_manifest_sha256=parent_sha,parser_input_sha256=pm['parser_input_sha256'],
                           covered_source_pages=sorted(cm['page_map'].values()))
            for candidate in payload['parser_candidates']:
                page=cm['page_map'].get(str(candidate.get('page')))
                if page is None:raise ValueError('Unmapped child parser page')
                candidate.setdefault('evidence',{}).update(child_parser_page=candidate['page'],child_parser_input_sha256=cm['parser_input_sha256'])
                candidate['page']=parent_index[page]
            target=out/'normalized'/p.name;atomic_json(target,payload)
            result[f'docling/{child.name}_{p.name}']=target
    return result
