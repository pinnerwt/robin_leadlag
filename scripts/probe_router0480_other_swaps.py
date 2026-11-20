"""Isolated0a/0d execution to the first external swap intent."""
import copy,json,re
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());rows=[]
 for prefix,opcode in [('0x78e95caa',10),('0x312801fc',13),('0x54e89943',10)]:
  original=next(json.loads(l)['tx'] for l in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if json.loads(l)['tx']['tx'].startswith(prefix));raw=bytearray.fromhex(original['data'][2:]);offsets=[int.from_bytes(raw[2+2*i:4+2*i],'big') for i in range(raw[0])];i=next(i for i,o in enumerate(offsets) if raw[o]==opcode);offset=offsets[i];stop=offsets[i+1];raw[0]=2;raw[1]=0;raw[2:6]=offset.to_bytes(2,'big')+offsets[-1].to_bytes(2,'big');tx=dict(original,data='0x'+raw.hex());s=copy.deepcopy(base);keep={tx['to'].lower(),tx['from'].lower(),'0x'+'00'*20};s['accounts']={a:v for a,v in s['accounts'].items() if a in keep or a[2:] in tx['data'].lower()};s.update(trace_execution=True,control_targets=[tx['to'].lower()],getters={});stages=[];assumed=[];mocks=[]
  for _ in range(6):
   r=run(s,tx);stages.append(r)
   if r['error'] and (m:=re.search(r'unknown account (0x[0-9a-fA-F]{40})',r['error'])):
    address=m.group(1).lower();s['accounts'][address]={'balance':'0x0','nonce':0,'code':'0x','storage':{}};assumed.append(address);continue
   if r['error'] or len(r['calls'])!=1:break
   c=r['calls'][0]
   if not c['data'].startswith('0x70a08231'):break
   s['getters'].setdefault(c['to'],{})[c['data']]='0x'+bytes(32).hex();mocks.append(c)
  rows.append(dict(original_tx=original,tx=tx,opcode=opcode,offset=offset,stop=stop,stages=stages,synthetic_account_metadata=assumed,synthetic_zero_inventory=mocks,result=r));print(prefix,r['error'],r['calls'])
 Path('reports/amm/router0480-other-swaps.json').write_text(json.dumps(dict(cases=rows,caveat='Command-table isolation, explicit account metadata and inventory substitutions. Intercepted intents only.'),indent=2)+'\n')
if __name__=='__main__':main()
