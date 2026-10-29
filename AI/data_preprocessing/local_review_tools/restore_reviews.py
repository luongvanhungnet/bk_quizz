"""Copy existing human events without changing their source/revision identities."""
from pathlib import Path
import argparse
from contextlib import closing
import json
import sqlite3

from ingest import digest,write_json
from serve import CachedReviewStore

ROOT=Path(__file__).resolve().parent


def copy_history(source,run,source_sha):
    source=Path(source).resolve();before=digest(source)
    with closing(sqlite3.connect('file:'+source.as_posix()+'?mode=ro',uri=True)) as old:
        events=old.execute('SELECT record_id,created_ns,review_id,payload FROM reviews ORDER BY created_ns').fetchall()
    for _,_,_,payload in events:
        if json.loads(payload).get('source_sha256')!=source_sha:raise ValueError('Human history belongs to another source')
    store=CachedReviewStore(run);inserted=0
    with store._connect() as new:
        for record_id,created_ns,review_id,payload in events:
            existing=new.execute('SELECT payload FROM reviews WHERE review_id=?',(review_id,)).fetchone()
            if existing:
                if existing[0]!=payload:raise ValueError('Conflicting human review event')
                continue
            new.execute('INSERT INTO reviews(record_id,created_ns,review_id,payload) VALUES(?,?,?,?)',
                        (record_id,created_ns,review_id,payload));inserted+=1
    if digest(source)!=before:raise ValueError('Original human database changed')
    return inserted


def main(workspace):
    workspace=Path(workspace)
    run_by_source={}
    for run in (workspace/'runs').iterdir():
        manifest=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
        run_by_source[manifest['document']['sha256']]=run
    before=json.loads((workspace/'unit_returns/existing_human_databases_before.json').read_text(encoding='utf-8'))
    result=[]
    for old in before:
        source=Path(old['path']);manifest=json.loads((source.parent/'manifest.json').read_text(encoding='utf-8'))
        sha=manifest['document']['sha256']
        if digest(source)!=old['sha256']:raise ValueError('Original human database changed')
        with closing(sqlite3.connect('file:'+source.as_posix()+'?mode=ro',uri=True)) as c:count=c.execute('SELECT COUNT(*) FROM reviews').fetchone()[0]
        if count and sha in run_by_source:
            run=run_by_source[sha];inserted=copy_history(source,run,sha)
            stats=CachedReviewStore(run).stats()
            result.append({'source':str(source),'destination':str(run/'human_reviews.sqlite3'),
                'source_events':count,'events_copied':inserted,'current_human_verified':stats['human_verified'],
                'stale_reviews':stats['stale_reviews'],'original_database_unchanged':True})
    write_json(workspace/'unit_returns/human_history_restored.json',{'events':result,'new_human_decisions_created':0})
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=ROOT.parent/'workspaces/unit100_v6_20261022')
    main(parser.parse_args().workspace)
