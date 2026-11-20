"""Isolate opcode08 with original operands; no full-transaction success claim."""
import copy,json
from pathlib import Path
from probe_delegated_kind8 import run
from router0480_first_swap import ROUTER

def main():
 base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());rows=[]
 for prefix in ('0xac088a83af','0x0b7ab3b8f6'):
  original=next(json.loads(l)['tx'] for l in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if json.loads(l)['tx']['tx'].startswith(prefix))
  raw=bytearray.fromhex(original['data'][2:]);offsets=[int.from_bytes(raw[2+2*i:4+2*i],'big') for i in range(raw[0])];i=next(i for i,o in enumerate(offsets) if raw[o]==8);offset=offsets[i];stop=offsets[i+1]
  raw[0]=2;raw[1]=0;raw[2:6]=offset.to_bytes(2,'big')+offsets[-1].to_bytes(2,'big');tx=dict(original,data='0x'+raw.hex());s=copy.deepcopy(base);s.update(trace_execution=True,getters={});stages=[]
  for _ in range(3):
   r=run(s,tx);stages.append(r)
   if r['error'] or len(r['calls'])!=1:break
   c=r['calls'][0]
   if not c['data'].startswith('0x70a08231'):break
   s['getters'].setdefault(c['to'],{})[c['data']]='0x'+bytes(32).hex()
  rows.append(dict(original_tx=original,command_offset=offset,command_stop=stop,stages=stages,result=r));print(prefix,r['error'],r['calls'])
 Path('reports/amm/router0480-wrap.json').write_text(json.dumps(dict(cases=rows,caveat='Isolated opcode08/a3. Zero inventory mocks; intercepted deposit intent only, no native funding or transaction success validation.'),indent=2)+'\n')
if __name__=='__main__':main()
