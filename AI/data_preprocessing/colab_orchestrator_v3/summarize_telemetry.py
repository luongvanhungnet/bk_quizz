"""Summarize measured spans/resources. No missing measurements are invented."""
import argparse
from collections import defaultdict
import json
from pathlib import Path


def summarize(paths):
    stages=defaultdict(lambda:{'calls':0,'seconds':0,'errors':0})
    peak_rss=0;min_available=None;peak_vram=None;processes={};exports=[];seen=set()
    for path in paths:
        with Path(path).open(encoding='utf-8') as f:
            for line in f:
                try:r=json.loads(line)
                except json.JSONDecodeError:continue  # Incomplete live tail is not a sample.
                key=(r.get('unix'),r.get('pid'),line)
                if key in seen:continue
                seen.add(key)
                if r['event']=='stage_end':
                    s=stages[r['stage']];s['calls']+=1;s['seconds']+=r['seconds'];s['errors']+=r['status']!='ok'
                if r['event']=='resources':
                    peak_rss=max(peak_rss,r.get('process_tree_rss_bytes',0))
                    available=r.get('available_ram_bytes')
                    if available is not None:min_available=available if min_available is None else min(min_available,available)
                    for p in r['processes']:
                        name=str(p['pid'])+':'+p['name'];processes[name]=max(processes.get(name,0),p['rss_bytes'])
                    for gpu in r['gpus']:
                        try:peak_vram=max(peak_vram if peak_vram is not None else 0,float(gpu['memory.used']))
                        except (KeyError,ValueError):pass
                if r['event']=='export_size':exports.append(r)
    return {'stages':dict(stages),'stage_seconds_note':'Nested spans overlap; do not sum all rows as wall time.',
            'peak_process_tree_rss_bytes':peak_rss or None,'minimum_available_ram_bytes':min_available,
            'peak_vram_mib':peak_vram,'process_peak_rss_bytes':processes,'exports':exports}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('paths',type=Path,nargs='+');a=p.parse_args()
    print(json.dumps(summarize(a.paths),ensure_ascii=False,indent=2))
