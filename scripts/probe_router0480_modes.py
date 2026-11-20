"""Compare observed opcode03 byte profiles to actual pool immutable getters."""
import json
from pathlib import Path
from probe_delegated_kind8 import run
from bootstrap_state import selector
from router0480_first_swap import ROUTER

def main():
 seed=json.loads(Path('captures/startup-v9-dependencies.json').read_text());rows=[];cache={}
 for line in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines():
  tx=json.loads(line)['tx']
  if (tx.get('to') or '').lower()!=ROUTER:continue
  raw=bytes.fromhex(tx['data'][2:]);offsets=[int.from_bytes(raw[2+2*i:4+2*i],'big') for i in range(raw[0])]
  for i,o in enumerate(offsets[:-1]):
   c=raw[o:offsets[i+1]]
   if len(c)!=14 or c[0]!=3:continue
   p=int.from_bytes(c[3:5],'big');pool='0x'+raw[p:p+20].hex()
   if pool not in cache:
    small=dict(seed,accounts={a:v for a,v in seed['accounts'].items() if a in (pool,tx['from'].lower(),'0x'+'00'*20)});g=run(small,dict(tx,to=pool,data=selector('fee()')));cache[pool]=dict(result=g,fee=int(g['output'],16) if g['execution_success'] and g['output'] else None)
   rows.append(dict(tx=tx['tx'],index=i,pool=pool,zero=c[1],mode=c[2],last_byte=c[13],fee=cache[pool]['fee']))
 report=dict(rows=rows,getters=cache,caveat='Immutable/profile correlation only; interpretation requires executed callback branch validation.');Path('reports/amm/router0480-modes.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(rows))
if __name__=='__main__':main()
