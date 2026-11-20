"""Isolate original opcode02 plus terminal a3; explicit command-table intervention."""
import json
from pathlib import Path
from probe_delegated_kind8 import run
from router0480_first_swap import ROUTER

def main():
 old=json.loads(Path('reports/amm/router0480-a4.json').read_text());raw=bytearray.fromhex(old['tx']['data'][2:]);offsets=[int.from_bytes(raw[2+2*i:4+2*i],'big') for i in range(raw[0])];v2=next(o for o in offsets if raw[o]==2);last=offsets[-1];raw[0]=2;raw[1]=0;raw[2:6]=v2.to_bytes(2,'big')+last.to_bytes(2,'big');tx=dict(old['tx'],data='0x'+raw.hex());seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());keep={ROUTER,tx['from'].lower(),'0x'+'00'*20};seed['accounts']={a:v for a,v in seed['accounts'].items() if a in keep or a[2:] in tx['data'].lower()};seed.update(trace_execution=True,getters={});stages=[];synthetic=[]
 for _ in range(3):
  r=run(seed,tx);stages.append(r)
  if r['error'] or len(r['calls'])!=1:break
  c=r['calls'][0]
  if not c['data'].startswith('0x70a08231'):break
  seed['getters'].setdefault(c['to'],{})[c['data']]='0x'+bytes(32).hex();synthetic.append(c)
 Path('reports/amm/router0480-v2-command.json').write_text(json.dumps(dict(tx=tx,original_tx=old['tx'],command_offset=v2,synthetic_zero_balances=synthetic,stages=stages,result=r,caveat='Isolated opcode02/a3 command table; original payment/guard flow removed. No original transaction or funded swap success claim.'),indent=2)+'\n');print(json.dumps(dict(error=r['error'],calls=r['calls'])))
if __name__=='__main__':main()
