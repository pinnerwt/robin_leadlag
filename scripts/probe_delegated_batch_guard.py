"""Offline explicit reentrancy-guard counterfactuals; never hydrate unknowns as zero."""
import copy,json
from pathlib import Path
from probe_delegated_kind8 import run
SLOT='0x9b779b17422d0df92223018b32b4d1fa46e071723d6817e2486d003becc55f00'
def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True
 baseline=json.loads(Path('reports/amm/delegated-batch-nested-prefix.json').read_text());cases=[]
 for entry in baseline['cases']:
  tx=entry['tx']
  for value in (0,1,2):
   s=copy.deepcopy(seed);s['accounts'][tx['to']]['storage'][SLOT]=hex(value)
   r=run(s,tx);cases.append(dict(tx=tx,synthetic_guard=value,result=r))
   print(tx['tx'][:14],value,r['error'],r['output'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 Path('reports/amm/delegated-batch-guard.json').write_text(json.dumps(dict(slot=SLOT,cases=cases,caveat='Explicit synthetic guard states only. Original missing-state evidence preserved. No approval or full batch execution.'),indent=2)+'\n')
if __name__=='__main__':main()
