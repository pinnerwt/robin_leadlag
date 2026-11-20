"""Independent per-leg math at saved checkpoint; no historical or settlement claim."""
import json
from pathlib import Path
from bootstrap_state import selector
from probe_delegated_kind8 import run
from variant_v3_checkpoint import load

def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());r=json.loads(Path('reports/amm/router0480-nested-paid.json').read_text());addresses=[x['call']['to'] for x in r['swaps']];tx=r['tx'];keep=set(addresses+[tx['from'].lower(),'0x'+'00'*20]);seed['accounts']={a:v for a,v in seed['accounts'].items() if a in keep};rows=[]
 for entry in r['swaps']:
  c=entry['call'];meta={}
  for name in ('token0','token1','fee','tickSpacing'):
   g=run(seed,dict(tx,to=c['to'],data=selector(name+'()')))
   if not g['execution_success'] or g['error']:raise ValueError('getter failed '+name)
   meta[name]=int(g['output'],16)
  d=bytes.fromhex(c['data'][10:]);state=load(seed['accounts'][c['to']]['storage'],meta['fee'],meta['tickSpacing']);error=None;fill=None
  try:fill=state.swap(bool(int.from_bytes(d[32:64],'big')),int.from_bytes(d[64:96],'big',signed=True),int.from_bytes(d[96:128],'big'))
  except ValueError as exc:error=str(exc)
  rows.append(dict(pool=c['to'],metadata=meta,fill=fill,error=error));print(c['to'],error,fill,flush=True)
 Path('reports/amm/router0480-curve-preview.json').write_text(json.dumps(dict(anchor=seed['anchor']['hash'],rows=rows,caveat='Original sizes at a saved checkpoint, not historical transaction state. Guard was mutated to expose route. Token settlement not modeled.'),indent=2)+'\n')
if __name__=='__main__':main()
