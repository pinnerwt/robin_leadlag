"""Synthetic offline bytecode experiment, NOT a historical execution replay.
Getter outputs and token accounts are deliberately stubbed to isolate balance cap.
"""
import sys,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from packed_routers import inspect_29,ROUTER_29
s=json.load(open('captures/router-prefix-checkpoint.json'))
for line in open('reports/amm/packed-router-corpus.jsonl'):
 t=json.loads(line)['tx']
 if t['to'].lower()!=ROUTER_29 or t['data'][2:10] not in ('9c909e3f','e22092ea'):continue
 ops=inspect_29(t['data'])
 if len(ops)==1 and ops[0]['pool_index']==0 and ops[0]['flags']==5:break
op=ops[0];pool='0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca';vault='2417c0170e63a1d41ec8d1d819b857f09e3d48bb';balcall='0x70a08231'+'0'*24+vault
results=[]
for balance in (op['requested_amount']+10,op['requested_amount']//2+1):
 s['getters']={pool:{'0x3850c7bd':'0x'+(op['limit']+1).to_bytes(32,'big').hex()}}
 for token in ('0x0bd7d308f8e1639fab988df18a8011f41eacad73','0x5fc973b2b5e1c609035b176e7d1c2444c47a0587'):
  s['getters'][token]={balcall:'0x'+balance.to_bytes(32,'big').hex()}
  s['accounts'][token]={'code':'0x00','balance':'0x0','nonce':'0x0','storage':{}}
 open('/tmp/probe29-seed.json','w').write(json.dumps(s))
 p=subprocess.run(['target/release/examples/router_prefix','/tmp/probe29-seed.json'],input=json.dumps(t)+'\n',text=True,capture_output=True,check=True)
 c=json.loads(p.stdout);assert not c['error'] and len(c['calls'])==1 and c['calls'][0]['data'].startswith('0x128acb08')
 actual=int(c['calls'][0]['data'][10+64*2:10+64*3],16)
 assert actual==min(op['requested_amount'],balance-1)
 results.append(dict(synthetic=True,stubbed_token_accounts=True,actual_amount=actual,tx=t,intent=op,synthetic_balance=balance,expected_amount=min(op['requested_amount'],balance-1),prefix=json.loads(p.stdout)))
open('reports/amm/router29-synthetic-probes.json','w').write(json.dumps(results,indent=2)+'\n')
for r in results:print(json.dumps(r['prefix']))
