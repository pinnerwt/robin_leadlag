"""Explicit inventory interventions after the separately marked guard mutation."""
import copy,json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 prior=json.loads(Path('reports/amm/router0480-guard-boundary.json').read_text());old=json.loads(Path('reports/amm/router0480-local-getters.json').read_text());base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());call=prior['result']['calls'][0];rows=[]
 # Preserve every known account needed by the tested calldata; no missing state default.
 for balance in (0,1000000,1000000000000):
  seed=copy.deepcopy(base);seed.update(trace_execution=True,execute_calls=old['execute_calls'],getters={call['to']:{call['data']:'0x'+balance.to_bytes(32,'big').hex()}})
  r=run(seed,prior['tx']);rows.append(dict(balance=balance,result=r));print(balance,r['error'],r['execution_success'],[(c['to'],c['data'][:10]) for c in r['calls']],flush=True)
 Path('reports/amm/router0480-inventory.json').write_text(json.dumps(dict(tx=prior['tx'],synthetic_inventory_call=call,cases=rows,caveat='Mutated guard threshold plus synthetic USDG inventory; no original transaction success claim.'),indent=2)+'\n')
if __name__=='__main__':main()
