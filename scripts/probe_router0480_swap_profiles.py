"""Isolated opcode direction/profile interventions; callback intentionally not run."""
import json
from pathlib import Path
from probe_delegated_kind8 import run
from router0480_guards import inspect
from router0480_first_swap import ROUTER

def main():
 prior=json.loads(Path('reports/amm/router0480-inventory.json').read_text());old=json.loads(Path('reports/amm/router0480-local-getters.json').read_text());seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());tx=prior['tx'];keep={ROUTER,tx['from'].lower(),'0x'+'00'*20};seed['accounts']={a:v for a,v in seed['accounts'].items() if a in keep or a[2:] in tx['data'].lower()};c=prior['synthetic_inventory_call'];seed.update(execute_calls=old['execute_calls'],getters={c['to']:{c['data']:'0x'+bytes(32).hex()}},trace_execution=True);rows=[];start=inspect(tx['data'])['offsets'][3]
 for zero in (0,1):
  for profile in (0,1,5,30):
   raw=bytearray.fromhex(tx['data'][2:]);raw[start+1]=zero;raw[start+13]=profile;t=dict(tx,data='0x'+raw.hex());r=run(seed,t);rows.append(dict(zero=zero,profile=profile,tx=t,result=r))
 Path('reports/amm/router0480-swap-profiles.json').write_text(json.dumps(dict(cases=rows,caveat='Synthetic direction/profile and guard interventions. Swap prefix only; callback registrations and pool metadata compatibility not inferred.'),indent=2)+'\n');print([(r['zero'],r['profile'],r['result']['error'],len(r['result']['calls'])) for r in rows])
if __name__=='__main__':main()
