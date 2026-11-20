"""Explicit gate counterfactual, not historical initialization or live reducer."""
import argparse,copy,json
from pathlib import Path
from probe_delegated_kind8 import run
from probe_delegated_batch_guard import SLOT

def main():
 ap=argparse.ArgumentParser();group=ap.add_mutually_exclusive_group();group.add_argument('--allow-profile',action='store_true');group.add_argument('--allow-signer',action='store_true');args=ap.parse_args()
 source='allow-profile' if args.allow_signer else 'gates' if args.allow_profile else 'guard'
 destination='allow-signer' if args.allow_signer else 'allow-profile' if args.allow_profile else 'gates'
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True;rows=[]
 prior=json.loads(Path('reports/amm/delegated-batch-'+source+'.json').read_text())
 for case in prior['cases']:
  if args.allow_profile or args.allow_signer:
   if not case['result'].get('error'):continue
  elif case['synthetic_guard']!=1:continue
  tx=case['tx'];gate=case['result']['storage_reads'][-1]['slot']
  for value in (0,1):
   s=copy.deepcopy(seed);patches={**(case.get('synthetic_patches') or {SLOT:'0x1'}),gate:hex(value)};s['accounts'][tx['to']]['storage'].update(patches)
   r=run(s,tx);rows.append(dict(tx=tx,synthetic_patches=patches,result=r))
   print(tx['tx'][:14],value,r['error'],r['output'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 Path('reports/amm/delegated-batch-'+destination+'.json').write_text(json.dumps(dict(cases=rows,caveat='Explicit synthetic guard and gate changes. No missing value is claimed as observed; original missing evidence remains separate.'),indent=2)+'\n')
if __name__=='__main__':main()
