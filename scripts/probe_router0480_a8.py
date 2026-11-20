"""Saved actual a2 guard getter path, no network or state substitutions."""
import json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 tx=next(json.loads(l)['tx'] for l in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if json.loads(l)['tx']['tx'].startswith('0xac088a83af'))
 raw=bytearray.fromhex(tx['data'][2:]);offsets=[int.from_bytes(raw[2+2*i:4+2*i],'big') for i in range(raw[0])];original=dict(tx);raw[0]=3;raw[1]=0;raw[2:8]=offsets[1].to_bytes(2,'big')+offsets[3].to_bytes(2,'big')+offsets[-1].to_bytes(2,'big');tx=dict(tx,data='0x'+raw.hex())
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());keep={tx['to'].lower(),tx['from'].lower(),'0x'+'00'*20};seed['accounts']={a:v for a,v in seed['accounts'].items() if a in keep or a[2:] in tx['data'].lower()};seed.update(trace_execution=True,control_targets=[tx['to'].lower()],execute_calls=[]);stages=[]
 for _ in range(5):
  r=run(seed,tx);stages.append(r)
  if r['error'] or len(r['calls'])!=1:break
  c=r['calls'][0];key=c['to']+':'+c['data']
  if c['scheme']!='StaticCall' or c['data'][:10] not in ('0x1e2eaeaf','0x3850c7bd') or key in seed['execute_calls']:break
  seed['execute_calls'].append(key)
 Path('reports/amm/router0480-a8.json').write_text(json.dumps(dict(original_tx=original,tx=tx,stages=stages,result=r,execute_calls=seed['execute_calls'],caveat='Command-table isolation of a8 and terminal a3; no price mocks. Not original full execution.'),indent=2)+'\n');print(json.dumps(dict(error=r['error'],success=r['execution_success'],calls=r['calls'])))
if __name__=='__main__':main()
