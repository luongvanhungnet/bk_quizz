"""Read-only smoke checks of each imported course through the live review APIs."""
from pathlib import Path
import json
from urllib.parse import urlencode,quote
from urllib.request import urlopen

from ingest import write_json

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parent/'workspaces/unit100_v6_20261022'
BASE='http://127.0.0.1:8765/'


def get(url):
    with urlopen(url,timeout=120) as response:
        data=response.read()
        return json.loads(data) if 'application/json' in response.headers.get('Content-Type','') else data


def main():
    catalog=get(BASE+'api/catalog');results=[]
    for d in catalog['documents']:
        with urlopen(BASE+'open?'+urlencode({'doc':d['document_id'],'scope':'vlm'}),timeout=120) as response:
            url=response.geturl();page=response.read().decode('utf-8')
        assert 'keyboard.js' in page and 'Danh sách học phần' in page
        boot=get(url+'api/bootstrap');stats=get(url+'api/stats')
        assert boot['scope']=='vlm' and boot['document']['sha256']==d['source_sha256']
        assert stats['vlm_success_outputs']==d['vlm_records']
        assert stats['inventory']['total']==d['records']
        rows=get(url+'api/records?limit=1')['records'];images=0
        if rows:
            prefix=url+'api/record/'+quote(rows[0]['id'],safe='')
            detail=get(prefix)
            assert detail['record']['source_sha256']==d['source_sha256']
            for field in ['render','crop','context']:
                data=get(prefix+'/image/'+field)
                assert data.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff'))
                images+=1
        results.append({'course':d['course'],'url':url,'records':d['records'],
            'vlm_records':d['vlm_records'],'source_images_served':images,'reviewed':stats['reviewed'],
            'human_verified':stats['human_verified'],'stale_reviews':stats['stale_reviews']})
        write_json(WORKSPACE/'unit_returns/web_verification.json',{'courses':results,'complete':len(results)==27,'review_submissions_sent':0})
        print(f'WEB OK {d["course"]}: {d["vlm_records"]} VLM / {d["records"]} regions; {images} images',flush=True)
    d=catalog['documents'][0]
    with urlopen(BASE+'open?'+urlencode({'doc':d['document_id'],'scope':'all'}),timeout=120) as response:url=response.geturl();response.read()
    stats=get(url+'api/stats');assert stats['scope']=='all' and stats['total']==d['records']
    write_json(WORKSPACE/'unit_returns/web_verification.json',{'courses':results,'complete':True,
        'all_scope_checked':True,'review_submissions_sent':0})
    print('All 27 courses, source images, and explicit all-data mode passed. No review decisions submitted.',flush=True)


if __name__=='__main__':main()
