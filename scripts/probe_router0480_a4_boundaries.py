"""Actual reserve-guard boundary comparisons, without token/state mocks."""
import json
from pathlib import Path
from probe_delegated_kind8 import run
from router0480_guards import inspect

def main():
 old=json.loads(Path('reports/amm/router0480-a4.json').read_text());seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());tx=old['tx'];g=inspect(tx['data'])['guards'][0];keep={g['pool'],tx['to'].lower(),tx['from'].lower(),'0x'+'00'*20};seed['accounts']={a:v for a,v in seed['accounts'].items() if a in keep};seed.update(trace_execution=True,control_targets=[tx['to'].lower()],execute_calls=old['execute_calls']);v=old['result']['execution_returns'][0]['output'];res=[int(v[i:i+64],16) for i in (2,66)];rows=[]
 for side in (0,1):
  for shift in (-1,0,1):
   raw=bytearray.fromhex(tx['data'][2:]);o=g['offset'];raw[o+1]=side
   for k,n in ((4,res[0]),(6,res[1]+shift)):
    p=int.from_bytes(raw[o+k:o+k+2],'big');raw[p:p+16]=n.to_bytes(16,'big')
   t=dict(tx,data='0x'+raw.hex());r=run(seed,t);rows.append(dict(side=side,shift=shift,tx=t,result=r))
 Path('reports/amm/router0480-a4-boundaries.json').write_text(json.dumps(dict(reserves=res,cases=rows,caveat='Reference/side calldata interventions. Real saved reserves; pass cases may stop on later missing account.'),indent=2)+'\n');print([(x['side'],x['shift'],x['result']['execution_success']) for x in rows])
if __name__=='__main__':main()
