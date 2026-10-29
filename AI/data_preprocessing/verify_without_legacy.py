"""Run a selected unittest suite while denying reads from retired dependency folders."""
from pathlib import Path
import argparse,sys,unittest
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('suite');p.add_argument('--pattern',default='test*.py');a=p.parse_args()
old=[ROOT/'AI/Qwen_cpt_version'/n for n in ['data_preprocessing','hybrid_preprocessing','region_preprocessing','region_preprocessing_v2','region_preprocessing_v3','region_preprocessing_v5','region_preprocessing_v5_official']]
old += [ROOT/'AI/data_preprocessing/uploads_14_sequential_20261021',ROOT/'AI/Qweun_sft_version/completed_sft_tools']
blocked=[str(x.resolve()).lower() for x in old]
def guard(event,args):
 if event in ('open','os.listdir','os.scandir') and args and isinstance(args[0],(str,bytes)):
  path=str(Path(__import__('os').fsdecode(args[0])).resolve()).lower()
  if any(path==x or path.startswith(x+'\\') for x in blocked):raise PermissionError('Retired dependency access: '+path)
sys.addaudithook(guard)
suite=Path(a.suite).resolve();sys.path.insert(0,str(suite))
result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(str(suite),pattern=a.pattern))
sys.exit(not result.wasSuccessful())
