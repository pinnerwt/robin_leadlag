"""Isolated unknown command discovery, using saved router bytecode only."""
import copy,json,re
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());rows=[]
 for prefix,opcode in [('0x78e95caa',0xc2),('0x54e89943',0xc2)]:
  tx=next(json.loads(l)['tx'] for l in Path('reports/amm/optimistic-target-corpus.jsonl').read_text().splitlines() if json.loads(l)['tx']['tx'].startswith(prefix));raw=bytearray.fromhex(tx['data'][2:]);offsets=[int.from_bytes(raw[2+2*i:4+2*i],'big') for i in range(raw[0])];offset=next(o for o in offsets if raw[o]==opcode);swap=next(o for o in offsets if raw[o]==3);chosen=sorted([offset,swap,offsets[-1]]);raw[0]=3;raw[1]=0;raw[2:8]=b''.join(o.to_bytes(2,'big') for o in chosen);probe=dict(tx,data='0x'+raw.hex());s=copy.deepcopy(base);keep={tx['to'].lower(),tx['from'].lower(),'0x'+'00'*20};s['accounts']={a:v for a,v in s['accounts'].items() if a in keep or a[2:] in tx['data'].lower()};s.update(trace_execution=True,control_targets=[tx['to'].lower()]);r=run(s,probe);baseline=r;assumed=[]
  if r['error'] and (m:=re.search(r'unknown account (0x[0-9a-fA-F]{40})',r['error'])):
   address=m.group(1).lower();s['accounts'][address]={'balance':'0x0','nonce':0,'code':'0x','storage':{}};assumed.append(address);r=run(s,probe)
  boundaries=[]
  for delta in (-1,0,1):
   changed=dict(probe,sequence=probe['sequence']+delta);boundaries.append(dict(sequence=changed['sequence'],result=run(s,changed)))
  rows.append(dict(boundaries=boundaries,original_tx=tx,tx=probe,opcode=opcode,offset=offset,baseline=baseline,synthetic_account_metadata=assumed,result=r));print(prefix,r['error'],r['calls'])
 Path('reports/amm/router0480-block-guard.json').write_text(json.dumps(dict(cases=rows,caveat='Isolated command tables; intercepted getter intent only, no original execution success.'),indent=2)+'\n')
if __name__=='__main__':main()
