"""Synthetic getter-word interventions; absent actual state stays absent."""
import json
from pathlib import Path
from probe_delegated_kind8 import run

def main():
 base=json.loads(Path('captures/startup-v9-dependencies.json').read_text());rows=[]
 for row in json.loads(Path('reports/amm/router0480-remaining-guards.json').read_text())['cases']:
  tx=row['tx'];raw=bytes.fromhex(tx['data'][2:]);o=row['offset'];lp=o+(36 if row['opcode']==172 else 4);ptr=int.from_bytes(raw[lp:lp+2],'big');limit=int.from_bytes(raw[ptr:ptr+(12 if row['opcode']==172 else 16)],'big');call=row['result']['calls'][0];keep={tx['to'].lower(),tx['from'].lower(),'0x'+'00'*20};s=dict(base,accounts={a:v for a,v in base['accounts'].items() if a in keep or a[2:] in tx['data'].lower()},trace_execution=True,control_targets=[tx['to'].lower()])
  for a in row['synthetic_account_metadata']:s['accounts'][a]={'balance':'0x0','nonce':0,'code':'0x','storage':{}}
  for side in (0,1):
   for delta in (-1,0,1):
    b=bytearray(raw);b[o+1]=side;price=limit+delta;packed=(price<<160)|12345 if row['opcode']==172 else ((price&((1<<104)-1))<<24)|((((price>>104)-0x8000)&0xffff)<<8);s['getters']={call['to']:{call['data']:'0x'+packed.to_bytes(32,'big').hex()}};r=run(s,dict(tx,data='0x'+b.hex()));rows.append(dict(tx=tx['tx'],opcode=row['opcode'],side=side,limit=limit,price=limit+delta,synthetic_packed_word=packed,result=r));print(tx['tx'][:12],side,delta,r['execution_success'],r['error'],[(c['data'][:10]) for c in r['calls']])
 Path('reports/amm/router0480-remaining-boundaries.json').write_text(json.dumps(dict(cases=rows,caveat='Synthetic packed getter return, command-table isolation and side interventions. Not actual pool prices or original transaction execution.'),indent=2)+'\n')
if __name__=='__main__':main()
