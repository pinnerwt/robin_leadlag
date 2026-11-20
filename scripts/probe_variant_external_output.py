"""Actual new-checkpoint external swap math with explicit token-transfer stub."""
import json,re
from pathlib import Path
from bootstrap_state import Bootstrap
from probe_delegated_kind8 import run

def main():
 prior=json.loads(Path('reports/amm/variant-external-storage-prefix.json').read_text());s=prior['seed'];tx=prior['tx'];s['getters']={};b=Bootstrap('https://rpc-robinhood.blockmachine.io');reads=[];synthetic=[];stages=[]
 for _ in range(16):
  r=run(s,tx);stages.append(r);error=r.get('error') or ''
  missing=re.search(r'unknown slot (0x[0-9a-fA-F]{40}) (0x[0-9a-fA-F]+)',error)
  if missing:
   address,slot=missing[1].lower(),missing[2];value=b.rpc('eth_getStorageAt',[address,slot,s['anchor']['number']]);s['accounts'][address]['storage'][slot]=value;reads.append(dict(address=address,slot=slot,value=value));continue
  missing=re.search(r'unknown account (0x[0-9a-fA-F]{40})',error)
  if missing:
   address=missing[1].lower();s['accounts'][address]=dict(code='0x',balance='0x0',nonce='0x0',storage={});synthetic.append(dict(kind='account',address=address));continue
  if len(r['calls'])==1 and r['calls'][0]['data'].startswith('0x23b872dd'):
   call=r['calls'][0];s['getters'].setdefault(call['to'],{})[call['data']]='0x'+(1).to_bytes(32,'big').hex();synthetic.append(dict(kind='transferFrom_success',call=call));continue
  break
 verified=b.rpc('eth_getBlockByNumber',[s['anchor']['number'],False])['hash']==s['anchor']['hash']
 Path('reports/amm/variant-external-output.json').write_text(json.dumps(dict(seed=s,tx=tx,reads=reads,synthetic=synthetic,stages=stages,result=r,anchor_verified=verified,caveat='Actual new-checkpoint swap code with synthetic caller/token payment. Not historical replay or complete execution.'),indent=2)+'\n')
 print(json.dumps(dict(reads=len(reads),error=r.get('error'),calls=r['calls'],output=r.get('output'),execution_calls=r.get('execution_calls',[])[-3:]),default=str))
if __name__=='__main__':main()
