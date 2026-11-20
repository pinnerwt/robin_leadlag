"""Explicit packed-slot interventions for a8, preserving real missing-slot baseline."""
import json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 old=json.loads(Path('reports/amm/router0480-a8.json').read_text());tx=old['tx'];call=old['stages'][0]['calls'][0];raw=bytes.fromhex(tx['data'][2:]);o=int.from_bytes(raw[2:4],'big');limitoff=int.from_bytes(raw[o+36:o+38],'big');limit=int.from_bytes(raw[limitoff:limitoff+20],'big');seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());keep={tx['to'].lower(),tx['from'].lower(),'0x'+'00'*20};seed['accounts']={a:v for a,v in seed['accounts'].items() if a in keep or a[2:] in tx['data'].lower()};seed.update(trace_execution=True,control_targets=[tx['to'].lower()]);rows=[]
 for side in (0,1):
  for shift in (-1,0,1):
   data=bytearray(raw);data[o+1]=side;t=dict(tx,data='0x'+data.hex());packed=(12345<<160)|(limit+shift);seed['getters']={call['to']:{call['data']:'0x'+packed.to_bytes(32,'big').hex()}};r=run(seed,t);rows.append(dict(tx=t,side=side,synthetic_packed_slot=packed,price=limit+shift,result=r))
 Path('reports/amm/router0480-a8-boundaries.json').write_text(json.dumps(dict(call=call,cases=rows,caveat='Synthetic manager slot word with high packed bits plus side/command-table interventions. Missing original slot remains unresolved.'),indent=2)+'\n');print([(x['side'],x['price']-limit,x['result']['error'],len(x['result']['calls'])) for x in rows])
if __name__=='__main__':main()
