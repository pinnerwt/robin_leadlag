"""Saved actual compressed-router execution; getters run locally, no mocks/RPC."""
import json
from pathlib import Path
from probe_delegated_kind8 import run
ROUTER='0x0480bafac5547926e8697de90d124b97d4a13f75'
def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());seed['trace_execution']=True;seed['trace_calldata']=True;seed['math_targets']=[ROUTER];seed['control_targets']=[ROUTER];seed['execute_calls']=[]
 row=next(json.loads(l) for l in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if (json.loads(l)['tx'].get('to') or '').lower()==ROUTER);stages=[]
 for _ in range(12):
  r=run(seed,row['tx']);stages.append(r)
  if r['error'] or len(r['calls'])!=1:break
  c=r['calls'][0]
  if c['scheme']!='StaticCall' or c['data'] not in ('0x3850c7bd','0x1a686502','0x0dfe1681','0xd21220a7','0xddca3f43'):break
  key=c['to']+':'+c['data']
  if key in seed['execute_calls']:break
  seed['execute_calls'].append(key)
 report=dict(tx=row['tx'],anchor=seed['anchor']['hash'],stages=stages,result=r,execute_calls=seed['execute_calls'],caveat='Actual saved code and known state only; getter execution isolated, no success or continuous-state claim.')
 Path('reports/amm/router0480-local-getters.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(stages=len(stages),error=r['error'],output=r['output'],calls=r['calls'])))
if __name__=='__main__':main()
