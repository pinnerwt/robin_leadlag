"""Two successful isolated hook calls with persisted hook writes; take is mocked."""
import json
from pathlib import Path
from probe_delegated_kind8 import run
from bootstrap_state import hashhex,mapping
from delegated_hook_fee import accounting_update

def main():
 full=json.loads(Path('captures/startup-v9-dependencies.json').read_text());source=json.loads(Path('reports/amm/delegated-settler-hook-take-success.json').read_text())['cases'][1]
 tx=source['tx'];hook=tx['to'];seed=dict(anchor=full['anchor'],trace_execution=True,getters=source['synthetic_getters'],accounts={a:v for a,v in full['accounts'].items() if a in (hook,tx['from'],'0x'+'00'*20)})
 d=bytes.fromhex(tx['data'][10:]);poolid=int(hashhex(d[32:192]),16)
 slots={f'slot{n}':mapping(0,int(mapping(poolid,n),16)) for n in (12,13)}
 config=int(json.loads(Path('reports/amm/delegated-hook-fee-fields.json').read_text())['original'],16);stages=[]
 for i in range(2):
  storage=seed['accounts'][hook]['storage'];expected=accounting_update({k:int(v,16) for k,v in storage.items()},config,source['synthetic_output'],**slots)
  result=run(seed,dict(tx,tx=tx['tx']+'-repeat-'+str(i)))
  if result['error'] or not result['execution_success']:raise ValueError('hook replay incomplete')
  actual={w['slot']:int(w['value'],16) for w in result['storage_writes'] if w['address']==hook}
  if actual!=expected['writes']:raise ValueError('accounting mismatch')
  stages.append(dict(expected=expected,result=result))
  for slot,value in actual.items():storage[slot]=hex(value)
 Path('reports/amm/delegated-hook-accounting.json').write_text(json.dumps(dict(anchor=full['anchor']['hash'],poolid=hex(poolid),slots=slots,stages=stages,caveat='Two identical isolated afterSwap scenarios. Exact manager.take mocked; only successful hook writes persisted. No complete pool or route replay.'),indent=2)+'\n')
 print('two sequential hook calls match local accounting')
if __name__=='__main__':main()
