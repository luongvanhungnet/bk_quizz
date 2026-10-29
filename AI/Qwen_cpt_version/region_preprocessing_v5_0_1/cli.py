"""v5 local workflow entry point; defaults never export unreviewed VLM facts."""
import argparse
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('prepare');q.add_argument('--pdf',type=Path,required=True);q.add_argument('--out',type=Path,required=True);q.add_argument('--pptx',type=Path)
    q=sub.add_parser('package');q.add_argument('--run',type=Path,required=True);q.add_argument('--out',type=Path,required=True);q.add_argument('--scope',choices=['pilot','all'],default='pilot');q.add_argument('--model',choices=['7b','3b'],default='7b');q.add_argument('--formula-crosscheck',action='store_true');q.add_argument('--all-visuals',action='store_true',help='Opt in to VLM on every visual candidate, including below-threshold/duplicate review items')
    q=sub.add_parser('merge');q.add_argument('--run',type=Path,required=True);q.add_argument('--packet',type=Path,required=True);q.add_argument('--results',type=Path,required=True)
    q=sub.add_parser('import-parser');q.add_argument('--run',type=Path,required=True);q.add_argument('--engine',choices=['docling','mineru','paddle'],required=True);q.add_argument('--input',type=Path,required=True);q.add_argument('--source-sha256',required=True)
    q=sub.add_parser('export');q.add_argument('--run',type=Path,required=True);q.add_argument('--out',type=Path,required=True);q.add_argument('--tokenizer',type=Path)
    a=p.parse_args()
    if a.command=='prepare':
        from prepare import prepare
        print(prepare(a.pdf,a.out,a.pptx))
    elif a.command=='package':
        from package_cloud import package
        print(package(a.run,a.out,a.scope,a.model,a.formula_crosscheck,a.all_visuals))
    elif a.command=='merge':
        from workflow import ingest_cloud
        print(json.dumps(ingest_cloud(a.run,a.results,a.packet),ensure_ascii=False,indent=2))
    elif a.command=='import-parser':
        from workflow import import_parser
        print(json.dumps(import_parser(a.run,a.engine,a.input,a.source_sha256),ensure_ascii=False,indent=2))
    else:
        from workflow import export_cpt
        print(json.dumps(export_cpt(a.run,a.out,a.tokenizer),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
