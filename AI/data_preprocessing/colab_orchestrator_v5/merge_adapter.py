"""Indexed equivalents of frozen merge code, guarded by exact source anchors."""
from collections import defaultdict
import inspect
from pathlib import Path

from region_policy import limit_candidates,hold_overflow_pages
from stage_guard import progress


def replace_once(source,old,new):
    if source.count(old)!=1:raise RuntimeError('Frozen merge anchor changed: '+old[:90])
    return source.replace(old,new,1)


def install():
    import batch_layout,workflow
    if getattr(batch_layout,'_v6_indexed',False):return
    source=inspect.getsource(batch_layout.materialize)
    source=replace_once(source,"known=set(r['id'] for r in rows);candidates=[];unmapped=[];parsed_pages=set()",
        "known=set(r['id'] for r in rows);candidates=[];unmapped=[];parsed_pages=set()\n"
        "    rows_by_page=defaultdict(list)\n    for r in rows:rows_by_page[r['page']].append(r)\n"
        "    requests_by_id={q['id']:q for q in pm['requests']}\n    _v6_progress('layout_read',records=len(rows))")
    source=replace_once(source,"next((q for q in pm['requests'] if q['id']==p.get('id')),None)","requests_by_id.get(p.get('id'))")
    source=replace_once(source,"with pymupdf.open(m['document']['path']) as pdf:",
        "candidates=limit_candidates(candidates,run)\n    hold_overflow_pages(rows,run)\n    _v6_progress('layout_materialize',candidates=len(candidates))\n    with pymupdf.open(m['document']['path']) as pdf:")
    source=replace_once(source,"matches=[r for r in rows if r['page']==c['page']", "matches=[r for r in rows_by_page[c['page']] if r['page']==c['page']")
    source=replace_once(source,'rows.append(r)',"rows.append(r);rows_by_page[r['page']].append(r)\n            if len(rows)%50==0:_v6_progress('layout_materialize',records=len(rows),page=c['page'])")
    # Hashes are memoized only within one immutable result/archive processing call.
    source=replace_once(source,"rows=jsonl(run/'records.jsonl');pages=", "hashes={}\n    raw_file_sha=file_sha\n    def once(path):\n        key=str(Path(path).resolve())\n        if key not in hashes:hashes[key]=raw_file_sha(path)\n        return hashes[key]\n    rows=jsonl(run/'records.jsonl');pages=")
    source=source.replace('file_sha(archive)','once(archive)').replace("file_sha(packet/'manifest.json')","once(packet/'manifest.json')")
    namespace={**batch_layout.materialize.__globals__,'defaultdict':defaultdict,'limit_candidates':limit_candidates,'hold_overflow_pages':hold_overflow_pages,'_v6_progress':progress}
    exec(compile(source,'v6_indexed_layout','exec'),namespace)
    batch_layout.materialize=namespace['materialize'];batch_layout._v6_indexed=True
    source=inspect.getsource(workflow.associate)
    source=replace_once(source,"added=0;unmatched=[];by_page={p:[r for r in records if r['page']==p] for p in {r['page'] for r in records}}",
        "added=0;unmatched=[];by_page=defaultdict(list)\n    for r in records:by_page[r['page']].append(r)")
    source=replace_once(source,"for r in records):", "for r in by_page.get(c['page'],[])):")
    namespace={**workflow.associate.__globals__,'defaultdict':defaultdict}
    exec(compile(source,'v6_indexed_association','exec'),namespace);workflow.associate=namespace['associate']
